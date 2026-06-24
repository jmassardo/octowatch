"""Post-setup restart orchestration.

After the setup wizard completes, all pods need to be restarted so they
load the newly-configured settings from the database overlay. This module
provides the logic to trigger rolling restarts of OctoWatch deployments
in the current namespace via the Kubernetes API.

The restart is executed as a background task AFTER the setup response is
sent to the user, so the setup wizard gets a successful response before
pods begin cycling.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)

# Label selector for OctoWatch deployments to restart
_LABEL_SELECTOR = "app.kubernetes.io/instance"


async def trigger_post_setup_restart() -> int:
    """Patch all OctoWatch deployments with a restartedAt annotation.

    This mimics ``kubectl rollout restart`` by setting the
    ``kubectl.kubernetes.io/restartedAt`` annotation on the pod template,
    causing a rolling update.

    Returns the number of deployments patched, or -1 if K8s API is unavailable.
    """
    try:
        from kubernetes import client, config
    except ImportError:
        logger.warning("post_setup_restart.kubernetes_not_installed")
        return -1

    namespace = os.environ.get("POD_NAMESPACE", "default")
    instance_name = os.environ.get("HELM_RELEASE_NAME", "octowatch")

    try:
        # Try in-cluster config first (running inside K8s)
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException:
            logger.warning("post_setup_restart.no_k8s_config")
            return -1

    apps_v1 = client.AppsV1Api()
    restart_time = datetime.now(UTC).isoformat()

    try:
        deployments = apps_v1.list_namespaced_deployment(
            namespace=namespace,
            label_selector=f"{_LABEL_SELECTOR}={instance_name}",
        )
    except Exception as exc:
        logger.error("post_setup_restart.list_failed", error=str(exc))
        return -1

    patched = 0
    for deploy in deployments.items:
        deploy_name = deploy.metadata.name

        # Skip the API deployment itself — it will be restarted last
        # to avoid killing the response connection
        if "-api" in deploy_name:
            continue

        try:
            patch_body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": restart_time,
                            }
                        }
                    }
                }
            }
            apps_v1.patch_namespaced_deployment(
                name=deploy_name,
                namespace=namespace,
                body=patch_body,
            )
            patched += 1
            logger.info("post_setup_restart.patched", deployment=deploy_name)
        except Exception as exc:
            logger.warning(
                "post_setup_restart.patch_failed",
                deployment=deploy_name,
                error=str(exc),
            )

    # Now restart the API deployment (self-restart — will roll gracefully)
    for deploy in deployments.items:
        deploy_name = deploy.metadata.name
        if "-api" in deploy_name:
            try:
                patch_body = {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "kubectl.kubernetes.io/restartedAt": restart_time,
                                }
                            }
                        }
                    }
                }
                apps_v1.patch_namespaced_deployment(
                    name=deploy_name,
                    namespace=namespace,
                    body=patch_body,
                )
                patched += 1
                logger.info("post_setup_restart.patched", deployment=deploy_name)
            except Exception as exc:
                logger.warning(
                    "post_setup_restart.patch_failed",
                    deployment=deploy_name,
                    error=str(exc),
                )

    logger.info("post_setup_restart.complete", patched=patched, total=len(deployments.items))
    return patched
