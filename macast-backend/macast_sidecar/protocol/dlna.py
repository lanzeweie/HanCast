"""
DLNA 协议 - 复用自 Macast-main/macast/protocol.py

改动点:
- 移除 CherryPy 依赖
- 提取为独立类
- 添加异步支持
- 集成 aiohttp 服务
"""

import re
import time
import uuid
import http.client
import logging
import threading
import requests
from lxml import etree
from queue import Queue
from typing import Optional, Dict, List, Callable
from ..types.device import Device

logger = logging.getLogger("macast.dlna")

NS_AVTRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
NS_RENDERING = "urn:schemas-upnp-org:service:RenderingControl:1"
NS_CONNECTION = "urn:schemas-upnp-org:service:ConnectionManager:1"

SERVICE_STATE_OBSERVED = {
    "AVTransport": ['TransportState',
                    'TransportStatus',
                    'CurrentMediaDuration',
                    'CurrentTrackDuration',
                    'CurrentTrack',
                    'NumberOfTracks'],
    "RenderingControl": ['Volume', 'Mute'],
    "ConnectionManager": ['A_ARG_TYPE_Direction',
                          'SinkProtocolInfo',
                          'CurrentConnectionIDs']
}


class ObserveClient:
    def __init__(self, service, url, timeout=1800):
        self.url = url
        self.service = service
        self.startTime = int(time.time())
        self.sid = f"uuid:{uuid.uuid4()}"
        self.timeout = timeout
        self.seq = 0
        self.host = re.findall(r"//([0-9:.]*)", url)[0]
        self.path = re.findall(r"//[0-9:.]*(.*)$", url)[0]
        self.error = 0

    def is_timeout(self):
        return int(time.time()) - self.startTime > self.timeout

    def update(self, timeout=1800):
        self.startTime = int(time.time())
        self.timeout = timeout

    def send_event_callback(self, data):
        """Sending event data to client"""
        headers = {"NT": "upnp:event",
                   "NTS": "upnp:propchange",
                   "CONTENT-TYPE": 'text/xml; charset="utf-8"',
                   "SID": self.sid,
                   "SEQ": self.seq,
                   "TIMEOUT": f"Second-{self.timeout}"
                   }
        namespace = 'urn:schemas-upnp-org:event-1-0'
        root = etree.Element(etree.QName(namespace, 'propertyset'),
                             nsmap={'e': namespace})
        if self.service == 'ConnectionManager':
            for i in data:
                prop = etree.SubElement(
                    root, '{urn:schemas-upnp-org:event-1-0}property')
                item = etree.SubElement(prop, i)
                item.text = str(data[i])
        else:
            prop = etree.SubElement(
                root, '{urn:schemas-upnp-org:event-1-0}property')
            last_change = etree.SubElement(prop, 'LastChange')
            event = etree.Element('Event')
            event.attrib['xmlns'] = 'urn:schemas-upnp-org:metadata-1-0/AVT/'
            instance_id = etree.SubElement(event, 'InstanceID')
            instance_id.set('val', '0')
            for i in data:
                p = etree.SubElement(instance_id, i)
                p.set('val', str(data[i]))
            last_change.text = etree.tostring(event, encoding="UTF-8").decode()
        data = etree.tostring(root, encoding="UTF-8")
        logger.debug("Prop Change---------")
        logger.debug(data)
        conn = http.client.HTTPConnection(self.host, timeout=5)
        conn.request("NOTIFY", self.path, data, headers)
        conn.close()
        self.seq = self.seq + 1


class Service:
    service_map = {}

    @classmethod
    def get(cls, name):
        return cls.service_map.get(name, Service(name))

    @classmethod
    def build(cls, name, ns, actions):
        cls.service_map[name] = Service(name, ns, actions)

    def __init__(self, name, namespace='', actions={}):
        self.name = name
        self.namespace = namespace
        self.actions = actions


class DLNAProtocol:
    """DLNA 协议实现"""

    def __init__(self):
        self._device: Optional[Device] = None
        self._control_url: Optional[str] = None
        self.running = False
        self.state_list = {}
        self.action_list = {}
        self.event_thread = None
        self.event_subscribes = {}  # subscribe devices
        self.state_queue = Queue()  # states needed be send to subscribe devices
        self.removed_device_queue = Queue()  # devices needed be removed
        self.append_device_queue = Queue()  # devices needed be added

        # 回调函数 (必须在 init_state 之前初始化)
        self._on_state_change: Optional[Callable[[str, any], None]] = None

        self.init_services()  # create services handle function from xml file
        self.init_state()  # set default value

    def set_callbacks(
        self,
        on_state_change: Optional[Callable[[str, any], None]] = None
    ):
        """设置回调函数"""
        self._on_state_change = on_state_change

    def init_state(self):
        """初始化状态"""
        self.set_state('CurrentPlayMode', 'NORMAL')
        self.set_state('TransportPlaySpeed', 1)
        self.set_state('TransportStatus', 'OK')
        self.set_state('RelativeCounterPosition', 2147483647)
        self.set_state('AbsoluteCounterPosition', 2147483647)
        self.set_state('A_ARG_TYPE_Direction', 'Output')
        self.set_state('CurrentConnectionIDs', '0')
        self.set_state('PlaybackStorageMedium', 'None')

    def init_services(self, xml_dir: str = None):
        """初始化服务"""
        import os
        if xml_dir is None:
            xml_dir = os.path.join(os.path.dirname(__file__), '..', 'xml')

        description = os.path.join(xml_dir, 'Description.xml')
        if not os.path.exists(description):
            logger.warning(f"Description.xml not found at {description}")
            return

        desc = etree.parse(description).getroot()
        for service_type in desc.iter('{urn:schemas-upnp-org:device-1-0}serviceType'):
            namespace = service_type.text
            service = service_type.text.split(":")[3]
            xml_path = os.path.join(xml_dir, f'{service}.xml')
            if os.path.exists(xml_path):
                self.build_action(namespace, service, etree.parse(xml_path).getroot())

    def build_action(self, namespace, service, xml):
        """Build action and variable list from xml file"""
        ns = '{urn:schemas-upnp-org:service-1-0}'
        # get state variable from xml file
        for state_variable in xml.iter(ns + 'stateVariable'):
            name = state_variable.find(ns + "name").text

            data = StateVariable(name,
                                 state_variable.attrib['sendEvents'],
                                 state_variable.find(ns + "dataType").text,
                                 service)
            default_value = state_variable.find(ns + "defaultValue")
            if default_value is not None:
                data.set_value(default_value.text)
            allowed_value_list = state_variable.find(ns + "allowedValueList")
            if allowed_value_list is not None:
                values = [
                    value.text
                    for value in allowed_value_list.findall(ns + "allowedValue")
                ]
                data.set_allowed_value_list(values)

            allowed_value_range = state_variable.find(ns + "allowedValueRange")
            if allowed_value_range is not None:
                data.set_allowed_value_range(
                    int(allowed_value_range.find(ns + "minimum").text),
                    int(allowed_value_range.find(ns + "maximum").text))
            self.state_list[name] = data

        # get action from xml file
        actions = {}
        for action in xml.iter(ns + 'action'):
            name = action.find(ns + "name").text
            input = []
            output = []
            argument_list = action.find(ns + "argumentList")
            if argument_list is not None:
                for argument in argument_list.findall(ns + 'argument'):
                    data = Argument(
                        argument.find(ns + "name").text,
                        argument.find(ns + "relatedStateVariable").text)
                    if argument.find(ns + "direction").text == 'in':
                        input.append(data)
                    else:
                        output.append(data)
            actions[name] = Action(name, input, output)
        Service.build(service, namespace, actions)

    def set_device(self, device: Device):
        """设置目标设备（用于控制端模式）"""
        self._device = device
        self._resolve_control_url()

    def play(self, media_uri: str = None, metadata: str = ""):
        """播放媒体"""
        if media_uri and self._device:
            # 设置 URI
            self._send_action(
                NS_AVTRANSPORT, "SetAVTransportURI",
                {
                    "InstanceID": 0,
                    "CurrentURI": media_uri,
                    "CurrentURIMetaData": metadata,
                }
            )
            self.set_state('CurrentTrackURI', media_uri)

        # 发送 Play
        if self._device:
            self._send_action(
                NS_AVTRANSPORT, "Play",
                {"InstanceID": 0, "Speed": 1}
            )
        self.set_state('TransportState', 'PLAYING')

    def stop(self):
        """停止播放"""
        if self._device:
            self._send_action(
                NS_AVTRANSPORT, "Stop",
                {"InstanceID": 0}
            )
        self.set_state('TransportState', 'STOPPED')

    def pause(self):
        """暂停播放"""
        if self._device:
            self._send_action(
                NS_AVTRANSPORT, "Pause",
                {"InstanceID": 0}
            )
        self.set_state('TransportState', 'PAUSED_PLAYBACK')

    def seek(self, position: str):
        """跳转到指定位置 (HH:MM:SS)"""
        if self._device:
            self._send_action(
                NS_AVTRANSPORT, "Seek",
                {
                    "InstanceID": 0,
                    "Unit": "REL_TIME",
                    "Target": position,
                }
            )
        self.set_state('RelativeTimePosition', position)
        self.set_state('AbsoluteTimePosition', position)

    def set_volume(self, volume: int):
        """设置音量 (0-100)"""
        if self._device:
            self._send_action(
                NS_RENDERING, "SetVolume",
                {
                    "InstanceID": 0,
                    "Channel": "Master",
                    "DesiredVolume": volume,
                }
            )
        self.set_state('Volume', volume)

    def set_mute(self, muted: bool):
        """设置静音"""
        if self._device:
            self._send_action(
                NS_RENDERING, "SetMute",
                {
                    "InstanceID": 0,
                    "Channel": "Master",
                    "DesiredMute": 1 if muted else 0,
                }
            )
        self.set_state('Mute', muted)

    def add_subscribe(self, service, url, timeout=1800):
        """Add a DLNA client to subscribe list"""
        logger.debug("SUBSCRIBE: " + url)
        for client in self.event_subscribes:
            if self.event_subscribes[client].url == url and \
                    self.event_subscribes[client].service == service:
                s = self.event_subscribes[client]
                s.update(timeout)
                logger.debug("SUBSCRIBE UPDATE")
                return {
                    "SID": s.sid,
                    "TIMEOUT": f"Second-{s.timeout}"
                }
        logger.debug("SUBSCRIBE ADD")
        client = ObserveClient(service, url, timeout)
        self.append_device_queue.put(client)
        threading.Thread(target=self.send_init_event,
                         kwargs={
                             'service': service,
                             'client': client
                         }).start()
        return {
            "SID": client.sid,
            "TIMEOUT": f"Second-{client.timeout}"
        }

    def send_init_event(self, service, client):
        """When there is a client subscription,
        the first event callback will send all the state values of the service."""
        data = {}
        for state in SERVICE_STATE_OBSERVED[service]:
            data[state] = self.state_list[state].value
        try:
            client.send_event_callback(data)
        except Exception as e:
            logger.error(str(e))

    def remove_subscribe(self, sid):
        """Remove a DLNA client from subscribe list"""
        if sid in self.event_subscribes:
            self.removed_device_queue.put(sid)
        return 200

    def renew_subscribe(self, sid, timeout=1800):
        """Renew a DLNA client in subscribe list"""
        if sid in self.event_subscribes:
            self.event_subscribes[sid].update(timeout)
            return 200
        return 412

    def send_states_to_clients(self, state_change_list):
        """Sending the states in the stateChangeList to the clients which subscribe to them."""
        if not bool(state_change_list):
            return
        # remove offline clients
        while not self.removed_device_queue.empty():
            sid = self.removed_device_queue.get()
            logger.info("Remove client: {}".format(sid))
            del self.event_subscribes[sid]
            self.removed_device_queue.task_done()
        # add clients
        while not self.append_device_queue.empty():
            client = self.append_device_queue.get()
            self.event_subscribes[client.sid] = client
            self.append_device_queue.task_done()
        # send stateChangeList to client
        for sid in self.event_subscribes:
            client = self.event_subscribes[sid]
            if client.is_timeout():
                self.remove_subscribe(client.sid)
                continue
            try:
                # Only send state which within the service
                state = {}
                for name in state_change_list:
                    if self.state_list[name].service == client.service:
                        state[name] = state_change_list[name]
                if len(state) == 0:
                    continue
                client.send_event_callback(state)

            except Exception as e:
                logger.error("send event error: " + str(e))
                client.error = client.error + 1
                if client.error > 10:
                    logger.debug("remove " + client.sid)
                    self.remove_subscribe(client.sid)

    def event(self):
        """DLNA Event thread
        If a DLNA client subscribes to the dlna event,
        it will automatically send the event to the client when the renderer state changes."""
        while self.running:
            if not self.state_queue.empty():
                state = {}
                while not self.state_queue.empty():
                    k, v = self.state_queue.get()
                    state[k] = v
                    self.state_queue.task_done()
                self.send_states_to_clients(state)
            time.sleep(1)

    def call(self, rawbody):
        """Processing requests from DLNA clients"""
        root = etree.fromstring(rawbody)[0][0]
        param = {}
        for node in root:
            param[node.tag] = node.text
        action = root.tag.split('}')[1]
        service = root.tag.split(":")[3]
        method = f"{service}_{action}"
        if method not in [
            'AVTransport_GetPositionInfo',
            'AVTransport_GetTransportInfo',
            'RenderingControl_GetVolume'
        ]:
            logger.info(f"{method} {param}")
        res = {}
        service_type = Service.get(service)
        if hasattr(self, method):
            data = {}
            input = service_type.actions[action].input
            for arg in input:
                data[arg.name] = Argument(
                    arg.name, arg.state,
                    param[arg.name] if arg.name in param else None)
                if arg.name in param:
                    self.set_state(arg.state, param[arg.name])
            res = getattr(self, method)(data)
        else:
            output = service_type.actions[action].output
            for arg in output:
                res[arg.name] = self.state_list[arg.state].value
        if method not in ['ConnectionManager_GetProtocolInfo', 'AVTransport_GetPositionInfo']:
            logger.info(f"res: {res}")

        # build response xml
        ns = 'http://schemas.xmlsoap.org/soap/envelope/'
        encoding = 'http://schemas.xmlsoap.org/soap/encoding/'
        root = etree.Element(etree.QName(ns, 'Envelope'), nsmap={'s': ns})
        root.attrib[f'{{{ns}}}encodingStyle'] = encoding
        body = etree.SubElement(root, etree.QName(ns, 'Body'), nsmap={'s': ns})
        response = etree.SubElement(body,
                                    etree.QName(
                                        service_type.namespace, f'{action}Response'),
                                    nsmap={'u': service_type.namespace})
        for key in res:
            prop = etree.SubElement(response, key)
            prop.text = str(res[key])
        return etree.tostring(root, encoding="UTF-8", xml_declaration=False)

    def set_state(self, name: str, value) -> None:
        """Set DLNA state which defined by xml file"""
        # update states which will send to DLNA Client
        if name in SERVICE_STATE_OBSERVED['AVTransport'] or \
                name in SERVICE_STATE_OBSERVED['RenderingControl']:
            logger.debug(f"setState: {name} {value}")
            # When some states change, the DLNA client needs to be notified immediately
            # We put this kind of state into state_queue, waiting to be sent to client.
            self.state_queue.put((name, value))

            # 触发回调
            if self._on_state_change:
                self._on_state_change(name, value)

        # update other states
        if name in self.state_list and self.state_list[name].value != value:
            self.state_list[name].value = value

    def get_state(self, name: str):
        """Get DLNA state"""
        if name in self.state_list:
            return self.state_list[name].value
        return ''

    def start(self):
        """Start render thread"""
        if self.running:
            return

        self.running = True
        self.event_thread = threading.Thread(target=self.event, daemon=True)
        self.event_thread.start()
        self.set_state_stop()

    def stop_event_thread(self):
        """Stop render thread"""
        self.running = False

    # The following method names are defined by the XML file

    def RenderingControl_SetVolume(self, data):
        volume = data['DesiredVolume']
        return {}

    def RenderingControl_SetMute(self, data):
        mute = data['DesiredMute']
        if mute.value == 0 or mute.value == '0':
            mute = False
        else:
            mute = True
        return {}

    def AVTransport_SetAVTransportURI(self, data):
        uri = data['CurrentURI'].value
        logger.info(uri)
        self.set_state_url(uri)
        title = "Macast"
        try:
            meta = etree.fromstring(data['CurrentURIMetaData'].value.encode())
            title_xml = meta.find('.//{{{}}}title'.format(meta.nsmap['dc']))
            if title_xml is not None and title_xml.text is not None:
                title = title_xml.text
            metadata = etree.tostring(meta, encoding="UTF-8", xml_declaration=False)
        except Exception as e:
            logger.error(str(e))
            logger.error(data['CurrentURIMetaData'].value)
            self.set_state('CurrentTrackMetaData', data['CurrentURIMetaData'].value)
        else:
            self.set_state('CurrentTrackMetaData', metadata.decode())
        self.set_state('CurrentTrackTitle', title)
        self.set_state('CurrentTrackURI', uri)
        self.set_state('RelativeTimePosition', '00:00:00')
        self.set_state('AbsoluteTimePosition', '00:00:00')
        self.set_state('TransportState', 'PAUSED_PLAYBACK')
        self.set_state('TransportStatus', 'OK')
        return {}

    def AVTransport_Play(self, data):
        self.set_state('TransportState', 'PLAYING')
        self.set_state('TransportStatus', 'OK')
        return {}

    def AVTransport_Pause(self, data):
        self.set_state('TransportState', 'PAUSED_PLAYBACK')
        return {}

    def AVTransport_Seek(self, data):
        target = data['Target']
        self.set_state('RelativeTimePosition', target.value)
        self.set_state('AbsoluteTimePosition', target.value)
        return {}

    def AVTransport_Stop(self, data):
        self.set_state('TransportState', 'STOPPED')
        return {}

    # The following methods are usually used to update the states of
    # DLNA Renderer according to the status obtained from the player.

    def set_state_position(self, data: str):
        self.set_state('RelativeTimePosition', data)
        self.set_state('AbsoluteTimePosition', data)

    def set_state_duration(self, data: str):
        self.set_state('CurrentTrackDuration', data)
        self.set_state('CurrentMediaDuration', data)

    def set_state_pause(self):
        self.set_state_transport('PAUSED_PLAYBACK')

    def set_state_play(self):
        self.set_state_transport('PLAYING')

    def set_state_stop(self):
        self.set_state_transport('STOPPED')

    def set_state_eof(self):
        self.set_state_transport('NO_MEDIA_PRESENT')

    def set_state_transport(self, data: str):
        self.set_state('TransportState', data)
        self.set_state('TransportStatus', 'OK')

    def set_state_transport_error(self):
        self.set_state('TransportState', 'STOPPED')
        self.set_state('TransportStatus', 'ERROR_OCCURRED')

    def set_state_mute(self, data: bool):
        self.set_state('Mute', data)

    def set_state_volume(self, data: int):
        self.set_state('Volume', data)

    def set_state_speed(self, data: str):
        self.set_state('TransportPlaySpeed', data)

    def set_state_display_subtitle(self, data: bool):
        self.set_state('DisplayCurrentSubtitle', data)

    def set_state_url(self, data: str):
        self.set_state('CurrentTrackURI', data)

    def get_state_title(self) -> str:
        return self.get_state('CurrentTrackTitle')

    def get_state_url(self) -> str:
        return self.get_state('CurrentTrackURI')

    def get_state_position(self) -> str:
        return self.get_state('RelativeTimePosition')

    def get_state_duration(self) -> str:
        return self.get_state('CurrentMediaDuration')

    def get_state_volume(self) -> int:
        return self.get_state('Volume')

    def get_state_mute(self) -> bool:
        return self.get_state('Mute')

    def get_state_transport_state(self) -> str:
        return self.get_state('TransportState')

    def get_state_transport_status(self) -> str:
        return self.get_state('TransportStatus')

    def get_state_speed(self) -> str:
        return self.get_state('TransportPlaySpeed')

    def get_state_display_subtitle(self) -> bool:
        return bool(self.get_state('DisplayCurrentSubtitle'))

    def _resolve_control_url(self):
        """解析设备的控制 URL"""
        if not self._device:
            return

        try:
            # 获取设备描述 XML
            resp = requests.get(f"http://{self._device.ip}:{self._device.port}/description.xml", timeout=5)
            root = etree.fromstring(resp.content)

            # 查找 AVTransport 服务
            ns = {"upnp": "urn:schemas-upnp-org:device-1-0"}
            for service in root.iter('{urn:schemas-upnp-org:device-1-0}service'):
                service_type = service.findtext('upnp:serviceType', '', ns)
                if 'AVTransport' in service_type:
                    control_url = service.findtext('upnp:controlURL', '', ns)
                    if control_url:
                        self._control_url = f"http://{self._device.ip}:{self._device.port}{control_url}"
                        logger.info(f"Control URL: {self._control_url}")
                        break
        except Exception as e:
            logger.error(f"Failed to resolve control URL: {e}")

    def _send_action(self, service: str, action: str, params: dict):
        """发送 SOAP 请求"""
        if not self._control_url:
            logger.error("No control URL")
            return

        # 构建 SOAP XML
        envelope = etree.Element(
            "{http://schemas.xmlsoap.org/soap/envelope/}Envelope"
        )
        body = etree.SubElement(
            envelope,
            "{http://schemas.xmlsoap.org/soap/envelope/}Body"
        )
        action_elem = etree.SubElement(
            body,
            f"{{{service}}}{action}"
        )

        for key, value in params.items():
            child = etree.SubElement(action_elem, key)
            child.text = str(value)

        xml_data = etree.tostring(envelope, xml_declaration=True, encoding="utf-8")

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service}#{action}"',
        }

        response = requests.post(
            self._control_url,
            data=xml_data,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        return etree.fromstring(response.content)


class DataType:
    boolean = 'boolean'
    i2 = 'i2'
    ui2 = 'ui2'
    i4 = 'i4'
    ui4 = 'ui4'
    string = 'string'


class StateVariable:
    """The state of render"""

    def __init__(self, name, send_events, datatype, service):
        self.name = name
        self.sendEvents = True if send_events == 'yes' else False
        self.datatype = datatype
        self.minimum = None
        self.maximum = None
        self.allowedValueList = None
        self.value = '' if self.datatype == 'string' else 0
        self.service = service

    def set_value(self, value):
        self.value = value

    def set_allowed_value_list(self, values):
        self.allowedValueList = values
        if 'NOT_IMPLEMENTED' in values:
            self.value = 'NOT_IMPLEMENTED'

    def set_allowed_value_range(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum


class Argument:
    def __init__(self, name, state, value=None):
        self.name = name
        self.state = state
        self.value = value


class Action:
    """Operations supported by render."""

    def __init__(self, name, input, output):
        self.name = name
        self.input = input
        self.output = output
