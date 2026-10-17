import { createNativeConditionalWorkerService } from "./native-conditional-worker-service.mjs";

const receive = createNativeConditionalWorkerService((value, transfer = []) => self.postMessage(value, transfer));
self.addEventListener("message", (event) => { void receive(event.data); });
