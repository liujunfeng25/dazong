import {
  getDeliveryCameraLiveUrlApi,
  postDeliveryCameraPtzApi,
  postDeliveryFleetCameraPtzApi,
  deliveryFleetMonitorCameraLiveUrlApi,
} from '../api/delivery'
import { monitorFleetMonitorCameraLiveUrlApi, monitorFleetMonitorCameraPtzApi } from '../api/monitor'
import {
  operationFleetMonitorCameraLiveUrlApi,
  operationFleetMonitorCameraPtzApi,
} from '../api/operation'

/** 萤石直播/云台 API：scope=delivery|monitor|operation，source=device|fleet */
export function useYs7CameraApis(scope = 'delivery', source = 'fleet') {
  const s = scope
  const liveUrlApi =
    source === 'device'
      ? getDeliveryCameraLiveUrlApi
      : s === 'operation'
        ? operationFleetMonitorCameraLiveUrlApi
        : s === 'monitor'
          ? monitorFleetMonitorCameraLiveUrlApi
          : deliveryFleetMonitorCameraLiveUrlApi

  const ptzControl =
    source === 'device'
      ? (id, payload) => postDeliveryCameraPtzApi(id, payload)
      : s === 'operation'
        ? (id, payload) => operationFleetMonitorCameraPtzApi(id, payload)
        : s === 'monitor'
          ? (id, payload) => monitorFleetMonitorCameraPtzApi(id, payload)
          : (id, payload) => postDeliveryFleetCameraPtzApi(id, payload)

  return { liveUrlApi, ptzControl }
}
