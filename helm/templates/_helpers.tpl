{{/*
octowatch Helm chart helpers
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "octowatch.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncate to 63 chars because Kubernetes name fields have a 63 character limit.
*/}}
{{- define "octowatch.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label value (name + version).
*/}}
{{- define "octowatch.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "octowatch.labels" -}}
helm.sh/chart: {{ include "octowatch.chart" . }}
{{ include "octowatch.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — used by Deployments and Services.
*/}}
{{- define "octowatch.selectorLabels" -}}
app.kubernetes.io/name: {{ include "octowatch.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API image reference.
Format: <registry>/octowatch-api:<tag>
Matches CI workflow which publishes ghcr.io/<owner>/octowatch-api:<branch/sha>.
*/}}
{{- define "octowatch.apiImage" -}}
{{- printf "%s/%s-api:%s" .Values.global.image.registry .Chart.Name .Values.global.image.tag }}
{{- end }}

{{/*
Worker image reference.
Format: <registry>/octowatch-worker:<tag>
*/}}
{{- define "octowatch.workerImage" -}}
{{- printf "%s/%s-worker:%s" .Values.global.image.registry .Chart.Name .Values.global.image.tag }}
{{- end }}

{{/*
Beat image reference.
Format: <registry>/octowatch-beat:<tag>
*/}}
{{- define "octowatch.beatImage" -}}
{{- printf "%s/%s-beat:%s" .Values.global.image.registry .Chart.Name .Values.global.image.tag }}
{{- end }}

{{/*
Frontend image reference.
Format: <registry>/octowatch-frontend:<tag>
*/}}
{{- define "octowatch.frontendImage" -}}
{{- printf "%s/%s-frontend:%s" .Values.global.image.registry .Chart.Name .Values.global.image.tag }}
{{- end }}

{{/*
Name of the Kubernetes Secret that holds application credentials.
*/}}
{{- define "octowatch.secretName" -}}
{{- printf "%s-secrets" (include "octowatch.fullname" .) }}
{{- end }}

{{/*
Name of the ConfigMap that holds non-secret application configuration.
*/}}
{{- define "octowatch.configMapName" -}}
{{- printf "%s-config" (include "octowatch.fullname" .) }}
{{- end }}

{{/*
Service account name. Uses serviceAccount.name if set, otherwise the chart fullname.
Gracefully handles missing serviceAccount values (not required in values.yaml).
*/}}
{{- define "octowatch.serviceAccountName" -}}
{{- if and .Values.serviceAccount .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "octowatch.fullname" . }}
{{- end }}
{{- end }}

{{/*
Soft (preferred) pod anti-affinity steering worker/beat pods away from nodes
that already run a Postgres primary — from this or any other customer
namespace sharing the cluster's nodes. Pairs with the matching preference on
the Postgres primary itself (templates/timescaledb.yaml) so the scheduler
avoids node-level CPU/IO contention between Celery workers and the DB they
depend on. Soft so pods never become unschedulable when every node already
runs a Postgres primary.
*/}}
{{- define "octowatch.avoidPostgresAffinity" -}}
podAntiAffinity:
  preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchExpressions:
            - key: app.kubernetes.io/component
              operator: In
              values:
                - postgresql
        namespaceSelector: {}
        topologyKey: kubernetes.io/hostname
{{- end }}
