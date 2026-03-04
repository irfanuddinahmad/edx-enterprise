"""
Helper functions for the Consent application.
"""

import logging
from urllib.parse import urlencode

from django.apps import apps
from django.urls import reverse

from consent.models import ProxyDataSharingConsent
from enterprise.api_client.discovery import get_course_catalog_api_service_client
from enterprise.utils import get_enterprise_customer

try:
    from openedx.features.enterprise_support.api import (
        CONSENT_FAILED_PARAMETER,
        consent_needed_for_course,
        enterprise_customer_uuid_for_request,
    )
except ImportError:
    CONSENT_FAILED_PARAMETER = 'consent_failed'
    consent_needed_for_course = None
    enterprise_customer_uuid_for_request = None

LOGGER = logging.getLogger(__name__)


def get_enterprise_consent_url(request, course_id, user=None, return_to=None, enrollment_exists=False, source='lms'):
    """
    Build a URL to redirect the user to the data-sharing consent page for a specific course.

    Arguments:
        request: Django request object.
        course_id: Course key/identifier string.
        user: user to check for consent. If None, uses ``request.user``.
        return_to: url name for the page to return to after consent is granted; defaults to
            ``request.path``.
        enrollment_exists: forwarded to ``consent_needed_for_course``.
        source: opaque string identifying the caller, recorded on the consent URL.
    """
    if consent_needed_for_course is None or enterprise_customer_uuid_for_request is None:
        return None
    user = user or request.user
    LOGGER.info(
        'Getting enterprise consent url for user [%s] and course [%s].',
        user.username,
        course_id,
    )
    if not consent_needed_for_course(request, user, course_id, enrollment_exists=enrollment_exists):
        return None
    return_path = request.path if return_to is None else reverse(return_to, args=(course_id,))
    url_params = {
        'enterprise_customer_uuid': enterprise_customer_uuid_for_request(request),
        'course_id': course_id,
        'source': source,
        'next': request.build_absolute_uri(return_path),
        'failure_url': request.build_absolute_uri(
            reverse('dashboard') + '?' + urlencode({CONSENT_FAILED_PARAMETER: course_id})
        ),
    }
    full_url = reverse('grant_data_sharing_permissions') + '?' + urlencode(url_params)
    LOGGER.info('Redirecting to %s to complete data sharing consent', full_url)
    return full_url


def get_data_sharing_consent(username, enterprise_customer_uuid, course_id=None, program_uuid=None):
    """
    Get the data sharing consent object associated with a certain user, enterprise customer, and other scope.

    :param username: The user that grants consent
    :param enterprise_customer_uuid: The consent requester
    :param course_id (optional): A course ID to which consent may be related
    :param program_uuid (optional): A program to which consent may be related
    :return: The data sharing consent object, or None if the enterprise customer for the given UUID does not exist.
    """
    EnterpriseCustomer = apps.get_model('enterprise', 'EnterpriseCustomer')
    try:
        if course_id:
            return get_course_data_sharing_consent(username, course_id, enterprise_customer_uuid)
        return get_program_data_sharing_consent(username, program_uuid, enterprise_customer_uuid)
    except EnterpriseCustomer.DoesNotExist:
        return None


def get_course_data_sharing_consent(username, course_id, enterprise_customer_uuid):
    """
    Get the data sharing consent object associated with a certain user of a customer for a course.

    :param username: The user that grants consent.
    :param course_id: The course for which consent is granted.
    :param enterprise_customer_uuid: The consent requester.
    :return: The data sharing consent object
    """
    # Prevent circular imports.
    DataSharingConsent = apps.get_model('consent', 'DataSharingConsent')
    return DataSharingConsent.objects.proxied_get(
        username=username,
        course_id=course_id,
        enterprise_customer__uuid=enterprise_customer_uuid
    )


def get_program_data_sharing_consent(username, program_uuid, enterprise_customer_uuid):
    """
    Get the data sharing consent object associated with a certain user of a customer for a program.

    :param username: The user that grants consent.
    :param program_uuid: The program for which consent is granted.
    :param enterprise_customer_uuid: The consent requester.
    :return: The data sharing consent object
    """
    enterprise_customer = get_enterprise_customer(enterprise_customer_uuid)
    discovery_client = get_course_catalog_api_service_client(enterprise_customer.site)
    course_ids = discovery_client.get_program_course_keys(program_uuid)
    child_consents = (
        get_data_sharing_consent(username, enterprise_customer_uuid, course_id=individual_course_id)
        for individual_course_id in course_ids
    )
    return ProxyDataSharingConsent.from_children(program_uuid, *child_consents)
