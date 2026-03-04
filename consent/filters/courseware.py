"""
Pipeline steps for courseware filters, contributed by the Consent app.
"""
from crum import get_current_request
from openedx_filters.filters import PipelineStep
from openedx_filters.learning.filters import CoursewareAccessChecksRequested

from consent.helpers import get_enterprise_consent_url


class ConsentRedirectStep(PipelineStep):
    """
    Sets the data-sharing consent redirect URL when the user has not yet consented.

    Registered against ``org.openedx.learning.courseware.view.started.v1``.
    Earlier steps win: if ``redirect_url`` is already set, this step is a no-op.
    """

    def run_filter(self, redirect_url, request, course_key):  # pylint: disable=arguments-differ
        if redirect_url is None:
            consent_url = get_enterprise_consent_url(request, str(course_key))
            if consent_url:
                redirect_url = consent_url
        return {"redirect_url": redirect_url, "request": request, "course_key": course_key}


class DataSharingConsentCheckStep(PipelineStep):
    """
    Deny courseware access when data sharing consent is required but not granted.

    Registered against ``org.openedx.learning.courseware.access_checks.requested.v1``.
    Raises ``CoursewareAccessChecksRequested.PreventCoursewareAccess`` to deny
    access when ``get_enterprise_consent_url`` returns a URL.
    """

    def run_filter(self, user, course_key):  # pylint: disable=arguments-differ
        request = get_current_request()
        if request is None:
            return {"user": user, "course_key": course_key}
        consent_url = get_enterprise_consent_url(request, str(course_key))
        if consent_url:
            raise CoursewareAccessChecksRequested.PreventCoursewareAccess(
                error_code="data_sharing_access_required",
                developer_message=consent_url,
                user_message="You must give Data Sharing Consent for the course",
            )
        return {"user": user, "course_key": course_key}
