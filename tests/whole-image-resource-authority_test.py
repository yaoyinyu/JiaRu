"""有界完整图发送的超限、未知及新旧资源政策回归。"""
import importlib.util
import unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location('whole_resource_fixture', Path(__file__).resolve().parents[1] / 'model/training/sample-whole-image-resource-window.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
POLICY = {'preparedRequestHardStopBytes': 100000000, 'batchImageFileAndPayloadLimitBytes': 8388608,
          'turnImageFileAndPayloadLimitBytes': 16777216, 'allowBoundedWholeImagesWhenRequestTelemetryUnavailable': True}
class ResourceAuthority(unittest.TestCase):
    def test_observed_oversize_never_falls_back_to_unknown_authorization(self):
        result = module.authorize(POLICY, 100000000, {'message': 'later metadata unavailable'}, 100, 0)
        self.assertTrue(result['observedRequestHardStop'])
        self.assertFalse(result['boundedWholeImageSendingAuthorized'])
        self.assertIsNone(result['measuredRequestGatePassed'])
    def test_unknown_is_authorized_bounded_but_not_measured_pass(self):
        result = module.authorize(POLICY, None, None, 200, 100)
        self.assertTrue(result['boundedWholeImageSendingAuthorized'])
        self.assertFalse(result['ok'])
        self.assertIsNone(result['measuredRequestGatePassed'])
    def test_turn_extension_does_not_extend_batch_or_request_hard_stop(self):
        old = {**POLICY, 'turnImageFileAndPayloadLimitBytes': 8388608}
        self.assertFalse(module.authorize(old, 9000000, None, 1380368, 7592355)['boundedWholeImageSendingAuthorized'])
        self.assertTrue(module.authorize(POLICY, 9000000, None, 1380368, 7592355)['boundedWholeImageSendingAuthorized'])
        self.assertFalse(module.authorize(POLICY, 9000000, None, 8388609, 0)['boundedWholeImageSendingAuthorized'])
        self.assertFalse(module.authorize(POLICY, 100000000, None, 1380368, 7592355)['boundedWholeImageSendingAuthorized'])
    def test_user_batch_only_cap_has_no_extra_turn_limit(self):
        user = {**POLICY, 'batchImageFileAndPayloadLimitBytes': 50000000,
                'turnImageFileAndPayloadLimitBytes': None}
        self.assertTrue(module.authorize(user, 15000000, None, 13086059, 8972723)['boundedWholeImageSendingAuthorized'])
        self.assertTrue(module.authorize(user, 15000000, None, 100, 50000000)['boundedWholeImageSendingAuthorized'])
        self.assertFalse(module.authorize(user, 15000000, None, 50000001, 0)['boundedWholeImageSendingAuthorized'])
        self.assertFalse(module.authorize(user, 100000000, None, 100, 0)['boundedWholeImageSendingAuthorized'])
if __name__ == '__main__': unittest.main()
