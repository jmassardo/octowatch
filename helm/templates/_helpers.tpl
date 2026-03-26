{{/*
audit-log-analyzer Helm chart helpers
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "audit-log-analyzer.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncate to 63 chars because Kubernetes name fields have a 63 character limit.
*/}}
{{- define "audit-log-analyzer.fullname" -}}
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
{{- define "audit-log-analyzer.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "audit-log-analyzer.labels" -}}
helm.sh/chart: {{ include "audit-log-analyzer.chart" . }}
{{ include "audit-log-analyzer.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — used by Deployments and Services.
*/}}
{{- define "audit-log-analyzer.selectorLabels" -}}
app.kubernetes.io/name: {{ include "audit-log-analyzer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API image reference.
Format: <registry>/<chart-name>/api:<tag>
*/}}
{{- define "audit-log-analyzer.apiImage" -}}
{{- printf "%s/%s/api:%s" .Values.global.image.registry .Chart.Name .Values.global.image.tag }}
{{- end }}

{{/*
Worker image reference.
*/}}
{{- define "audit-log-analyzer.workerImage" -}}
{{- printf "%s/%s/worker:%s" .Values.global.image.registry .Chart.Name .Values.global.image.tag }}
{{- end }}

{{/*
Frontend image reference.
*/}}
{{- define "audit-log-analyzer.frontendImage" -}}
{{- printf "%s/%s/frontend:%s" .Values.global.image.registry .Chart.Name .Values.global.image.tag }}
{{- end }}

{{/*
Name of the Kubernetes Secret that holds application credentials.
*/}}
{{- define "audit-log-analyzer.secretName" -}}
{{- printf "%s-secrets" (include "audit-log-analyzer.fullname" .) }}
{{- end }}

{{/*
Name of the ConfigMap that holds non-secret application configuration.
*/}}
{{- define "audit-log-analyzer.configMapName" -}}
{{- printf "%s-config" (include "audit-log-analyzer.fullname" .) }}
{{- end }}

{{/*
Service account name. Uses serviceAccount.name if set, otherwise the chart fullname.
Gracefully handles missing serviceAccount values (not required in values.yaml).
*/}}
{{- define "audit-log-analyzer.serviceAccountName" -}}
{{- if and .Values.serviceAccount .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "audit-log-analyzer.fullname" . }}
{{- end }}
{{- end }}
