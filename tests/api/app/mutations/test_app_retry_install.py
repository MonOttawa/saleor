from unittest.mock import Mock

import graphene

from saleor.app.models import AppInstallation
from saleor.core import JobStatus
from saleor.graphql.core.enums import AppErrorCode
from tests.api.utils import get_graphql_content

RETRY_INSTALL_APP_MUTATION = """
    mutation AppRetryInstall(
        $id: ID!, $activate_after_installation: Boolean){
        appRetryInstall(id:$id, activateAfterInstallation:$activate_after_installation){
            appInstallation{
                id
                status
                appName
                manifestUrl
            }
            appErrors{
                field
                message
                code
                permissions
            }
        }
    }
"""


def test_retry_install_app_mutation(
    monkeypatch,
    app_installation,
    permission_manage_apps,
    staff_api_client,
    permission_manage_orders,
    staff_user,
):
    app_installation.status = JobStatus.FAILED
    app_installation.save()
    mocked_task = Mock()
    monkeypatch.setattr(
        "saleor.graphql.app.mutations.install_app_task.delay", mocked_task
    )
    query = RETRY_INSTALL_APP_MUTATION
    staff_user.user_permissions.set([permission_manage_apps, permission_manage_orders])
    id = graphene.Node.to_global_id("AppInstallation", app_installation.id)
    variables = {
        "id": id,
        "activate_after_installation": True,
    }
    response = staff_api_client.post_graphql(query, variables=variables,)
    content = get_graphql_content(response)
    app_installation = AppInstallation.objects.get()
    app_installation_data = content["data"]["appRetryInstall"]["appInstallation"]
    _, app_id = graphene.Node.from_global_id(app_installation_data["id"])
    assert int(app_id) == app_installation.id
    assert app_installation_data["status"] == JobStatus.PENDING.upper()
    assert app_installation_data["manifestUrl"] == app_installation.manifest_url
    mocked_task.assert_called_with(app_installation.pk, True)


def test_retry_install_app_mutation_by_app(
    permission_manage_apps,
    permission_manage_orders,
    app_api_client,
    monkeypatch,
    app_installation,
):
    app_installation.status = JobStatus.FAILED
    app_installation.save()
    mocked_task = Mock()
    monkeypatch.setattr(
        "saleor.graphql.app.mutations.install_app_task.delay", mocked_task
    )
    id = graphene.Node.to_global_id("AppInstallation", app_installation.id)
    query = RETRY_INSTALL_APP_MUTATION
    app_api_client.app.permissions.set(
        [permission_manage_apps, permission_manage_orders]
    )
    variables = {
        "id": id,
        "activate_after_installation": False,
    }
    response = app_api_client.post_graphql(query, variables=variables,)
    content = get_graphql_content(response)
    app_installation = AppInstallation.objects.get()
    app_installation_data = content["data"]["appRetryInstall"]["appInstallation"]
    _, app_id = graphene.Node.from_global_id(app_installation_data["id"])
    assert int(app_id) == app_installation.id
    assert app_installation_data["status"] == JobStatus.PENDING.upper()
    assert app_installation_data["manifestUrl"] == app_installation.manifest_url
    mocked_task.assert_called_with(app_installation.pk, False)


def test_retry_install_app_mutation_missing_required_permissions(
    permission_manage_apps,
    staff_api_client,
    staff_user,
    app_installation,
    permission_manage_orders,
):
    app_installation.status = JobStatus.FAILED
    app_installation.permissions.add(permission_manage_orders)
    app_installation.save()

    query = RETRY_INSTALL_APP_MUTATION

    staff_user.user_permissions.set([permission_manage_apps])

    id = graphene.Node.to_global_id("AppInstallation", app_installation.id)
    variables = {
        "id": id,
    }
    response = staff_api_client.post_graphql(query, variables=variables,)
    content = get_graphql_content(response)
    data = content["data"]["appRetryInstall"]

    errors = data["appErrors"]
    assert not data["appInstallation"]
    assert len(errors) == 1
    error = errors[0]
    assert error["field"] == "id"
    assert error["code"] == AppErrorCode.OUT_OF_SCOPE_APP.name


def test_retry_install_app_mutation_by_app_missing_required_permissions(
    permission_manage_apps, app_api_client, app_installation, permission_manage_orders
):
    app_installation.status = JobStatus.FAILED
    app_installation.permissions.add(permission_manage_orders)
    app_installation.save()
    query = RETRY_INSTALL_APP_MUTATION
    app_api_client.app.permissions.set([permission_manage_apps])
    id = graphene.Node.to_global_id("AppInstallation", app_installation.id)
    variables = {
        "id": id,
    }
    response = app_api_client.post_graphql(query, variables=variables,)

    content = get_graphql_content(response)
    data = content["data"]["appRetryInstall"]

    errors = data["appErrors"]
    assert not data["appInstallation"]
    assert len(errors) == 1
    error = errors[0]
    assert error["field"] == "id"
    assert error["code"] == AppErrorCode.OUT_OF_SCOPE_APP.name


def test_cannot_retry_installation_if_status_is_different_than_failed(
    monkeypatch,
    app_installation,
    permission_manage_apps,
    staff_api_client,
    permission_manage_orders,
    staff_user,
):
    app_installation.status = JobStatus.PENDING
    app_installation.save()

    mocked_task = Mock()
    monkeypatch.setattr(
        "saleor.graphql.app.mutations.install_app_task.delay", mocked_task
    )
    query = RETRY_INSTALL_APP_MUTATION
    staff_user.user_permissions.set([permission_manage_apps, permission_manage_orders])
    id = graphene.Node.to_global_id("AppInstallation", app_installation.id)
    variables = {
        "id": id,
        "activate_after_installation": True,
    }
    response = staff_api_client.post_graphql(query, variables=variables,)
    content = get_graphql_content(response)

    AppInstallation.objects.get()
    app_installation_data = content["data"]["appRetryInstall"]["appInstallation"]
    app_installation_errors = content["data"]["appRetryInstall"]["appErrors"]
    assert not app_installation_data
    assert len(app_installation_errors) == 1
    assert app_installation_errors[0]["field"] == "id"
    assert app_installation_errors[0]["code"] == AppErrorCode.INVALID_STATUS.name

    assert not mocked_task.called