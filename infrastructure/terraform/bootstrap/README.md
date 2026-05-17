# Bootstrap — backend remoto (S3 + DynamoDB lock)

**Obligatorio una vez por cuenta AWS** antes de `terraform apply` en el stack principal.

Crea:

- **S3** `prode-terraform-state-<account_id>` (versionado, cifrado, sin acceso público)
- **DynamoDB** `prode-terraform-state-lock` (lock del state)

Este directorio usa **estado local** (el bucket aún no existe).

## Ejecutar

Desde `infrastructure/terraform`:

```bash
export AWS_PROFILE=asap_dev
./bin/bootstrap.sh
```

O manualmente:

```bash
cd infrastructure/terraform/bootstrap
terraform init -input=false
terraform apply -input=false
```

Luego, en el directorio padre:

```bash
cd ..
./bin/init-backend.sh
```
