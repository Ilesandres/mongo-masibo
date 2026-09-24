variable "org_id" {
  description = "ID de la organización en MongoDB Atlas (Project Settings > API Keys)."
  type        = string
}

variable "mongodbatlas_public_key" {
  description = "Clave pública de la API de MongoDB Atlas."
  type        = string
}

variable "mongodbatlas_private_key" {
  description = "Clave privada de la API de MongoDB Atlas (sensible)."
  type        = string
  sensitive   = true
}

variable "project_name" {
  description = "Nombre del proyecto Atlas que agrupa los recursos."
  type        = string
  default     = "Hyperflix-IPT"
}

variable "cluster_name" {
  description = "Nombre del clúster MongoDB."
  type        = string
  default     = "HyperflixCluster"
}

variable "backing_provider_name" {
  description = "Proveedor nube de respaldo (AWS/GCP/AZURE)."
  type        = string
  default     = "AWS"
}

variable "provider_region" {
  description = "Región del proveedor (p. ej. US_EAST_1, GCP_US_EAST4 o AZURE_EAST_2)."
  type        = string
  default     = "US_EAST_1"
}

variable "cluster_tier" {
  description = "Tier del clúster: M0/M2/M5 (TENANT) o M10/AWS para producción."
  type        = string
  default     = "M0"
}

variable "db_user" {
  description = "Nombre del usuario de base de datos de la aplicación."
  type        = string
  default     = "hyperflix_app"
}

variable "db_password" {
  description = "Contraseña del usuario de base de datos (sensible)."
  type        = string
  sensitive   = true
}