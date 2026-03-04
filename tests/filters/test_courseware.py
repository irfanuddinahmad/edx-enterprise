"""
Tests for enterprise.filters.courseware pipeline steps.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase
from openedx_filters.learning.filters import CoursewareAccessChecksRequested

from enterprise.filters.courseware import ActiveEnterpriseCheckStep, StartDateAccessFailureStep


class TestStartDateAccessFailureStep(TestCase):
    """Tests for StartDateAccessFailureStep."""

    def _make_step(self):
        return StartDateAccessFailureStep(
            "org.openedx.learning.course.start_date.validation_failed.v1", []
        )

    @patch('enterprise.filters.courseware.EnterpriseCustomerUser.objects')
    @patch(
        'enterprise.filters.courseware.enterprise_customer_from_session_or_learner_data',
        return_value={'uuid': 'abc-123'},
    )
    def test_sets_error_fields_for_enterprise_learner(self, mock_customer, mock_ecu_objects):
        """error_code and messages are populated for enterprise learners with no error set."""
        mock_ecu_objects.filter.return_value.exists.return_value = True
        step = self._make_step()
        request = MagicMock()
        request.user.id = 42
        result = step.run_filter(
            error_code=None,
            developer_message=None,
            user_message=None,
            request=request,
            course_key=MagicMock(),
        )
        self.assertEqual(result['error_code'], 'course_not_started_enterprise_learner')
        self.assertIsNotNone(result['developer_message'])
        self.assertIsNotNone(result['user_message'])

    @patch(
        'enterprise.filters.courseware.enterprise_customer_from_session_or_learner_data',
        return_value=None,
    )
    def test_passes_through_when_no_enterprise_customer(self, mock_customer):
        """Inputs are unchanged when there is no active enterprise customer."""
        step = self._make_step()
        request = MagicMock()
        result = step.run_filter(
            error_code=None,
            developer_message=None,
            user_message=None,
            request=request,
            course_key=MagicMock(),
        )
        self.assertIsNone(result['error_code'])
        self.assertIsNone(result['developer_message'])
        self.assertIsNone(result['user_message'])

    @patch(
        'enterprise.filters.courseware.enterprise_customer_from_session_or_learner_data',
        return_value={'uuid': 'abc-123'},
    )
    def test_preserves_existing_error_code(self, mock_customer):
        """If a prior step already set error_code, this step does not overwrite it."""
        step = self._make_step()
        request = MagicMock()
        result = step.run_filter(
            error_code='already_set',
            developer_message='dev',
            user_message='user',
            request=request,
            course_key=MagicMock(),
        )
        self.assertEqual(result['error_code'], 'already_set')
        self.assertEqual(result['developer_message'], 'dev')
        self.assertEqual(result['user_message'], 'user')


class TestActiveEnterpriseCheckStep(TestCase):
    """Tests for ActiveEnterpriseCheckStep."""

    def _make_step(self):
        return ActiveEnterpriseCheckStep(
            "org.openedx.learning.courseware.access_checks.requested.v1", [],
        )

    @patch('enterprise.filters.courseware.EnterpriseCourseEnrollment.objects')
    def test_no_enterprise_enrollments_passthrough(self, mock_ece_objects):
        """When the user has no enterprise enrollments, the step is a no-op."""
        mock_ece_objects.filter.return_value.exists.return_value = False
        step = self._make_step()
        user = MagicMock(id=42)
        course_key = MagicMock()
        result = step.run_filter(user=user, course_key=course_key)
        self.assertEqual(result, {"user": user, "course_key": course_key})

    @patch('enterprise.filters.courseware.EnterpriseCustomerUser.objects')
    @patch('enterprise.filters.courseware.EnterpriseCourseEnrollment.objects')
    def test_matching_active_customer_passthrough(self, mock_ece_objects, mock_ecu_objects):
        """When the active EnterpriseCustomerUser matches the enrollment's customer, no exception."""
        enterprise_enrollments = MagicMock()
        enterprise_enrollments.exists.return_value = True
        enterprise_enrollments.filter.return_value.exists.return_value = True
        mock_ece_objects.filter.return_value = enterprise_enrollments
        mock_ecu_objects.get.return_value = MagicMock()
        step = self._make_step()
        user = MagicMock(id=42)
        course_key = MagicMock()
        result = step.run_filter(user=user, course_key=course_key)
        self.assertEqual(result, {"user": user, "course_key": course_key})

    @patch('enterprise.filters.courseware.EnterpriseCustomerUser.objects')
    @patch('enterprise.filters.courseware.EnterpriseCourseEnrollment.objects')
    def test_mismatched_active_customer_raises(self, mock_ece_objects, mock_ecu_objects):
        """When the active EnterpriseCustomerUser does not match, PreventCoursewareAccess is raised."""
        enterprise_enrollments = MagicMock()
        enterprise_enrollments.exists.return_value = True
        enterprise_enrollments.filter.return_value.exists.return_value = False
        enterprise_enrollments.first.return_value.enterprise_customer_user.enterprise_customer.name = "EnrolledCo"
        mock_ece_objects.filter.return_value = enterprise_enrollments
        active_ecu = MagicMock()
        active_ecu.enterprise_customer.name = "ActiveCo"
        mock_ecu_objects.get.return_value = active_ecu
        step = self._make_step()
        with self.assertRaises(CoursewareAccessChecksRequested.PreventCoursewareAccess) as ctx:
            step.run_filter(user=MagicMock(id=42), course_key=MagicMock())
        self.assertEqual(ctx.exception.error_code, "incorrect_active_enterprise")
        self.assertIn("EnrolledCo", ctx.exception.user_message)
        self.assertIn("ActiveCo", ctx.exception.user_message)
