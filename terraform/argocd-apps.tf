# terraform/argocd-apps.tf
# ArgoCD Application CRD for OctoWatch — managed by Terraform on initial bootstrap.
# After bootstrap, ArgoCD manages its own lifecycle (self-heal enabled).

resource "kubernetes_manifest" "octowatch_argocd_app" {
  manifest = {
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata = {
      name      = "octowatch"
      namespace = "argocd"
      annotations = {
        "argocd-image-updater.argoproj.io/image-list"                = "api=ghcr.io/jmassardo/octowatch/api,worker=ghcr.io/jmassardo/octowatch/worker,beat=ghcr.io/jmassardo/octowatch/beat,frontend=ghcr.io/jmassardo/octowatch/frontend"
        "argocd-image-updater.argoproj.io/api.update-strategy"      = "semver"
        "argocd-image-updater.argoproj.io/worker.update-strategy"   = "semver"
        "argocd-image-updater.argoproj.io/beat.update-strategy"     = "semver"
        "argocd-image-updater.argoproj.io/frontend.update-strategy" = "semver"
        "argocd-image-updater.argoproj.io/write-back-method"        = "git"
        "argocd-image-updater.argoproj.io/git-branch"               = "main"
        "argocd-image-updater.argoproj.io/write-back-target"        = "helmvalues:helm/values-image-tag.yaml"
      }
    }
    spec = {
      project = "default"
      source = {
        repoURL        = "https://github.com/jmassardo/octowatch.git"
        targetRevision = "HEAD"
        path           = "helm"
        helm = {
          releaseName = "octowatch"
          valueFiles  = ["values.yaml", "values-azure.yaml", "values-image-tag.yaml"]
        }
      }
      destination = {
        server    = "https://kubernetes.default.svc"
        namespace = "octowatch"
      }
      syncPolicy = {
        automated = {
          prune    = true
          selfHeal = true
        }
        syncOptions = ["CreateNamespace=true"]
      }
      ignoreDifferences = [
        {
          group        = "apps"
          kind         = "Deployment"
          jsonPointers = ["/spec/replicas"]
        },
        {
          group        = ""
          kind         = "Secret"
          name         = "octowatch-secrets"
          jsonPointers = ["/data", "/stringData"]
        },
        {
          group        = ""
          kind         = "Secret"
          name         = "octowatch-db-secret"
          jsonPointers = ["/data", "/stringData"]
        },
        {
          group        = ""
          kind         = "Secret"
          name         = "octowatch-valkey-secret"
          jsonPointers = ["/data", "/stringData"]
        },
        {
          group        = ""
          kind         = "Secret"
          name         = "octowatch-github-app-key"
          jsonPointers = ["/data", "/stringData"]
        },
        {
          group        = ""
          kind         = "Secret"
          name         = "ghcr-pull-secret"
          jsonPointers = ["/data", "/stringData"]
        }
      ]
    }
  }
  depends_on = [helm_release.argocd, kubernetes_namespace.octowatch]
}
