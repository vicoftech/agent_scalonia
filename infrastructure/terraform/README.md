# Terraform — Data layer (Sprint 0+)

- **DynamoDB** `ProdeTable-<env>`: módulo `terraform-aws-modules/dynamodb-table/aws` (~> 4.x), billing on-demand, PITR, TTL `ttl_expiry`, stream `NEW_AND_OLD_IMAGES`, 4 GSIs.
- **Cognito** User Pool + app client público: recursos `aws_cognito_*` del proveedor HashiCorp AWS (paridad con el antiguo CDK `DataStack`).

## Uso local

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars   # no commitear tfvars con secretos
terraform init
terraform plan -var=env=staging
terraform apply -var=env=staging
```

## CI / deploy

Los workflows ejecutan `terraform init` + `apply` en el runner. **Sin backend remoto (S3 + DynamoDB lock), el estado no persiste entre ejecuciones** y el apply no es usable en producción. Ver `backend.tf.example` y configurá `terraform init` con `-backend-config=...` o un `backend.tf` local no versionado.

GitHub Actions usa las credenciales AWS del environment (`staging` / `production`).

## Outputs

Tras el apply: `dynamodb_table_name`, `dynamodb_table_arn`, `dynamodb_stream_arn`, `cognito_user_pool_id`, `cognito_app_client_id`.
