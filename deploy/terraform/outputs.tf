output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "プライベートサブネットID"
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "パブリックサブネットID"
  value       = module.vpc.public_subnets
}

output "eks_cluster_name" {
  description = "EKSクラスター名"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKSクラスターエンドポイント"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_security_group_id" {
  description = "EKSクラスターセキュリティグループID"
  value       = module.eks.cluster_security_group_id
}

output "rds_endpoint" {
  description = "RDSエンドポイント"
  value       = module.rds.db_instance_endpoint
}

output "rds_database_name" {
  description = "RDSデータベース名"
  value       = module.rds.db_instance_name
}

output "redis_endpoint" {
  description = "Redisエンドポイント"
  value       = module.elasticache.cluster_address
}

output "s3_bucket_name" {
  description = "S3バケット名"
  value       = aws_s3_bucket.audio_storage.bucket
}

output "s3_bucket_arn" {
  description = "S3バケットARN"
  value       = aws_s3_bucket.audio_storage.arn
}

output "cloudfront_distribution_id" {
  description = "CloudFrontディストリビューションID"
  value       = aws_cloudfront_distribution.cdn.id
}

output "cloudfront_domain_name" {
  description = "CloudFrontドメイン名"
  value       = aws_cloudfront_distribution.cdn.domain_name
}

output "app_role_arn" {
  description = "アプリケーションIAMロールARN"
  value       = aws_iam_role.app_role.arn
}
