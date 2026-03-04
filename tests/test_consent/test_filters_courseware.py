"""
Tests for consent.filters.courseware pipeline steps.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase
from openedx_filters.learning.filters import CoursewareAccessChecksRequested

from consent.filters.courseware import ConsentRedirectStep, DataSharingConsentCheckStep


class TestConsentRedirectStep(TestCase):
    """Tests for ConsentRedirectStep."""

    def _make_step(self):
        return ConsentRedirectStep(
            "org.openedx.learning.courseware.view.started.v1", []
        )

    @patch('consent.filters.courseware.get_enterprise_consent_url', return_value='/consent/')
    def test_sets_consent_url_when_required(self, mock_get_url):
        """redirect_url is populated when get_enterprise_consent_url returns a URL."""
        step = self._make_step()
        request = MagicMock()
        course_key = MagicMock()
        course_key.__str__ = lambda s: 'course-v1:org+course+run'
        result = step.run_filter(redirect_url=None, request=request, course_key=course_key)
        self.assertEqual(result['redirect_url'], '/consent/')

    @patch('consent.filters.courseware.get_enterprise_consent_url', return_value=None)
    def test_passes_through_when_no_consent_required(self, mock_get_url):
        """redirect_url remains None when consent is not required."""
        step = self._make_step()
        request = MagicMock()
        course_key = MagicMock()
        course_key.__str__ = lambda s: 'course-v1:org+course+run'
        result = step.run_filter(redirect_url=None, request=request, course_key=course_key)
        self.assertIsNone(result['redirect_url'])

    @patch('consent.filters.courseware.get_enterprise_consent_url', return_value='/consent/')
    def test_preserves_existing_redirect_url(self, mock_get_url):
        """If a prior step already set redirect_url, this step does not overwrite it."""
        step = self._make_step()
        request = MagicMock()
        course_key = MagicMock()
        course_key.__str__ = lambda s: 'course-v1:org+course+run'
        result = step.run_filter(
            redirect_url='/already/set/',
            request=request,
            course_key=course_key,
        )
        self.assertEqual(result['redirect_url'], '/already/set/')
        mock_get_url.assert_not_called()


class TestDataSharingConsentCheckStep(TestCase):
    """Tests for DataSharingConsentCheckStep."""

    def _make_step(self):
        return DataSharingConsentCheckStep(
            "org.openedx.learning.courseware.access_checks.requested.v1", [],
        )

    @patch('consent.filters.courseware.get_enterprise_consent_url', return_value='/consent/')
    @patch('consent.filters.courseware.get_current_request')
    def test_raises_when_consent_required(self, mock_get_request, mock_get_url):
        """Raises PreventCoursewareAccess when get_enterprise_consent_url returns a URL."""
        mock_get_request.return_value = MagicMock()
        step = self._make_step()
        user = MagicMock(id=42)
        course_key = MagicMock()
        course_key.__str__ = lambda s: 'course-v1:org+course+run'
        with self.assertRaises(CoursewareAccessChecksRequested.PreventCoursewareAccess) as ctx:
            step.run_filter(user=user, course_key=course_key)
        self.assertEqual(ctx.exception.error_code, 'data_sharing_access_required')
        self.assertEqual(ctx.exception.developer_message, '/consent/')

    @patch('consent.filters.courseware.get_enterprise_consent_url', return_value=None)
    @patch('consent.filters.courseware.get_current_request')
    def test_passthrough_when_consent_not_required(self, mock_get_request, mock_get_url):
        """No exception when consent is not required."""
        mock_get_request.return_value = MagicMock()
        step = self._make_step()
        user = MagicMock(id=42)
        course_key = MagicMock()
        course_key.__str__ = lambda s: 'course-v1:org+course+run'
        result = step.run_filter(user=user, course_key=course_key)
        self.assertEqual(result, {"user": user, "course_key": course_key})

    @patch('consent.filters.courseware.get_current_request', return_value=None)
    def test_passthrough_when_no_request(self, mock_get_request):
        """No exception when there is no current request available."""
        step = self._make_step()
        user = MagicMock(id=42)
        course_key = MagicMock()
        result = step.run_filter(user=user, course_key=course_key)
        self.assertEqual(result, {"user": user, "course_key": course_key})
