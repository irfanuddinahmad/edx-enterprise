"""
Pipeline steps for courseware-related openedx-filters contributed by the Enterprise app.
"""
import logging

from openedx_filters.filters import PipelineStep
from openedx_filters.learning.filters import CoursewareAccessChecksRequested

try:
    from openedx.features.enterprise_support.api import enterprise_customer_from_session_or_learner_data
except ImportError:
    enterprise_customer_from_session_or_learner_data = None

from enterprise.models import EnterpriseCourseEnrollment, EnterpriseCustomerUser

log = logging.getLogger(__name__)


class StartDateAccessFailureStep(PipelineStep):
    """
    Substitutes a more specific start-date access-error payload for enterprise learners.

    Registered against ``org.openedx.learning.course.start_date.validation_failed.v1``.
    If ``error_code`` is already set (an earlier step won) or the request user is not
    associated with the active session enterprise customer, this step passes through
    unchanged.
    """

    def run_filter(
        self,
        error_code,
        developer_message,
        user_message,
        request,
        course_key,
    ):  # pylint: disable=arguments-differ
        if error_code is None and enterprise_customer_from_session_or_learner_data is not None:
            enterprise_customer = enterprise_customer_from_session_or_learner_data(request)
            if enterprise_customer:
                user = request.user
                is_enterprise_learner = EnterpriseCustomerUser.objects.filter(
                    user_id=user.id,
                    enterprise_customer__uuid=enterprise_customer.get('uuid'),
                ).exists()
                if is_enterprise_learner:
                    error_code = "course_not_started_enterprise_learner"
                    developer_message = (
                        f"Course does not start until {course_key}, and the learner is "
                        "enrolled via an enterprise subsidy."
                    )
                    user_message = "Course has not started"
        return {
            "error_code": error_code,
            "developer_message": developer_message,
            "user_message": user_message,
            "request": request,
            "course_key": course_key,
        }


class ActiveEnterpriseCheckStep(PipelineStep):
    """
    Deny access when the learner's active EnterpriseCustomer differs from the
    EnterpriseCustomer attached to their EnterpriseCourseEnrollment for this course.

    Registered against ``org.openedx.learning.courseware.access_checks.requested.v1``.
    Raises ``CoursewareAccessChecksRequested.PreventCoursewareAccess`` to deny access.
    """

    def run_filter(self, user, course_key):  # pylint: disable=arguments-differ
        enterprise_enrollments = EnterpriseCourseEnrollment.objects.filter(
            course_id=course_key, enterprise_customer_user__user_id=user.id,
        )
        if not enterprise_enrollments.exists():
            return {"user": user, "course_key": course_key}

        try:
            active_ecu = EnterpriseCustomerUser.objects.get(user_id=user.id, active=True)
            if enterprise_enrollments.filter(enterprise_customer_user=active_ecu).exists():
                return {"user": user, "course_key": course_key}
            active_enterprise_name = active_ecu.enterprise_customer.name
        except (EnterpriseCustomerUser.DoesNotExist, EnterpriseCustomerUser.MultipleObjectsReturned):
            log.error("Multiple or No Active Enterprise found for the user %s.", user.id)
            active_enterprise_name = "Incorrect"

        enrollment_enterprise_name = (
            enterprise_enrollments.first().enterprise_customer_user.enterprise_customer.name
        )
        user_message = (
            "You are enrolled in this course with '{enrollment_enterprise_name}'. However, you are "
            "currently logged in as a '{active_enterprise_name}' user. Please log in with "
            "'{enrollment_enterprise_name}' to access this course."
        ).format(
            enrollment_enterprise_name=enrollment_enterprise_name,
            active_enterprise_name=active_enterprise_name,
        )
        raise CoursewareAccessChecksRequested.PreventCoursewareAccess(
            error_code="incorrect_active_enterprise",
            developer_message=(
                "User active enterprise should be same as EnterpriseCourseEnrollment enterprise."
            ),
            user_message=user_message,
        )
