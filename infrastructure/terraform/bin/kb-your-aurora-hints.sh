#!/usr/bin/env bash
# Imprime valores sugeridos para dev.tfvars (KB en TU Aurora).
# Uso: AWS_PROFILE=tu_profile ./bin/kb-your-aurora-hints.sh [cluster-id]
set -euo pipefail
CLUSTER="${1:-aurora-pg-dev}"
REGION="${AWS_REGION:-us-east-1}"

echo "Profile: ${AWS_PROFILE:-default}  Region: $REGION  Cluster: $CLUSTER"
echo ""

aws rds describe-db-clusters --db-cluster-identifier "$CLUSTER" \
  --query 'DBClusters[0].{Endpoint:Endpoint,DB:DatabaseName,Members:length(DBClusterMembers)}' \
  --output table

INST=$(aws rds describe-db-instances --filters "Name=db-cluster-id,Values=$CLUSTER" \
  --query 'DBInstances[0].DBInstanceIdentifier' --output text 2>/dev/null || echo "")
if [[ -n "$INST" && "$INST" != "None" ]]; then
  aws rds describe-db-instances --db-instance-identifier "$INST" \
    --query 'DBInstances[0].{Public:PubliclyAccessible,VpcId:DBSubnetGroup.VpcId,SG:VpcSecurityGroups[0].VpcSecurityGroupId}' \
    --output table
  VPC=$(aws rds describe-db-instances --db-instance-identifier "$INST" \
    --query 'DBInstances[0].DBSubnetGroup.VpcId' --output text)
  echo ""
  echo "Subnets del cluster (poner en lambda_vpc_subnet_ids):"
  aws rds describe-db-subnet-groups \
    --db-subnet-group-name "$(aws rds describe-db-instances --db-instance-identifier "$INST" --query 'DBInstances[0].DBSubnetGroup.DBSubnetGroupName' --output text)" \
    --query 'DBSubnetGroups[0].Subnets[*].SubnetIdentifier' --output text
  echo ""
  echo "kb_aurora_security_group_id = SG del Aurora (arriba)"
  echo "lambda_vpc_subnet_ids       = subnets arriba (misma VPC $VPC)"
  echo "lambda_vpc_security_group_ids = SG nuevo o existente para Lambdas KB en $VPC"
fi

echo ""
echo "Copiar a dev.tfvars:"
echo "  rds_proxy_endpoint = <Endpoint del cluster>"
echo "  db_name            = <DatabaseName>"
echo "  manage_aurora_secret = true   # o aurora_sync_secret_arn si ya tenés secret"
