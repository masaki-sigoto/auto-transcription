variable "project_name" {
  description = "プロジェクト名"
  type        = string
  default     = "transcription-app"
}

variable "environment" {
  description = "環境（development, staging, production）"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "環境は development, staging, production のいずれかである必要があります。"
  }
}

variable "aws_region" {
  description = "AWSリージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "availability_zones" {
  description = "使用するアベイラビリティーゾーン"
  type        = list(string)
  default     = ["ap-northeast-1a", "ap-northeast-1c", "ap-northeast-1d"]
}

variable "vpc_cidr" {
  description = "VPCのCIDRブロック"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  description = "プライベートサブネットのCIDRブロック"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "パブリックサブネットのCIDRブロック"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

variable "rds_instance_class" {
  description = "RDSインスタンスクラス"
  type        = string
  default     = "db.t3.large"
}

variable "redis_node_type" {
  description = "Redisノードタイプ"
  type        = string
  default     = "cache.t3.medium"
}

variable "eks_admin_roles" {
  description = "EKS管理者IAMロール"
  type = list(object({
    rolearn  = string
    username = string
    groups   = list(string)
  }))
  default = []
}

variable "domain_name" {
  description = "アプリケーションのドメイン名"
  type        = string
  default     = "transcription-app.example.com"
}
