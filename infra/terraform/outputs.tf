# Salidas útiles tras `terraform apply`
output "project_id" {
  description = "ID del proyecto creado en MongoDB Atlas."
  value       = mongodbatlas_project.hyperflix.id
}

output "cluster_name" {
  description = "Nombre del clúster aprovisionado."
  value       = mongodbatlas_cluster.hyperflix.name
}

output "cluster_tier" {
  description = "Tier aprovisionado."
  value       = mongodbatlas_cluster.hyperflix.provider_instance_size_name
}

output "mongo_uri_srv" {
  description = "URI de conexión (SRV) para config.py (.env: MONGO_URI)."
  value       = mongodbatlas_cluster.hyperflix.connection_strings[0].standard_srv
  sensitive   = true
}