# ──────────────────────────────────────────────────────────────
# Terraform — Infraestructura como Código (IaC) para Hyperflix
# Aprovisiona de forma reproducible el proyecto + clúster MongoDB
# Atlas + usuario de base de datos (sin clics en la consola web).
#
# Requiere: terraform >= 1.5 y llaves de la API de MongoDB Atlas.
# Uso (desde infra/terraform):
#   terraform init
#   terraform plan     # revisar
#   terraform apply    # aprovisionar
# ──────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.5"
  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 1.22"
    }
  }
}

provider "mongodbatlas" {
  public_key  = var.mongodbatlas_public_key
  private_key = var.mongodbatlas_private_key
}

# Proyecto: agrupa todos los recursos del sistema (una sola facturación)
resource "mongodbatlas_project" "hyperflix" {
  name   = var.project_name
  org_id = var.org_id
}

# Clúster: tier gratuito M0 por defecto (escalable a M2/M5/M10)
resource "mongodbatlas_cluster" "hyperflix" {
  project_id                  = mongodbatlas_project.hyperflix.id
  name                        = var.cluster_name
  provider_name               = "TENANT"
  backing_provider_name       = var.backing_provider_name
  provider_instance_size_name = var.cluster_tier
  provider_region_name        = var.provider_region
}

# Usuario de aplicación con credenciales propias
resource "mongodbatlas_database_user" "hyperflix_app" {
  project_id         = mongodbatlas_project.hyperflix.id
  username           = var.db_user
  password           = var.db_password
  auth_database_name = "admin"
  roles {
    role_name     = "readWriteAnyDatabase"
    database_name = "admin"
  }
}