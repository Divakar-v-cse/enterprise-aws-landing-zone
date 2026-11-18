###############################################################################
# Networking module - VPC, subnets, routing, NAT, NACLs, security groups
#
# Segmentation model
#   public  subnets : only load balancers / ingress. No public IPs handed out
#                     automatically (map_public_ip_on_launch = false).
#   private subnets : all workloads. No inbound path from the internet.
#   NAT     subnets : egress path, optional (billable), disabled by default.
#   S3      endpoint: free gateway endpoint keeps S3 traffic off the NAT.
###############################################################################

locals {
  tags = merge(var.tags, {
    Module      = "networking"
    Environment = var.environment
  })

  az_list = slice(var.availability_zones, 0, min(var.az_count, length(var.availability_zones)))

  # Number of NAT gateways actually created (0 when disabled).
  nat_count = var.enable_nat_gateway ? (var.single_nat_gateway ? 1 : length(local.az_list)) : 0

  # Public NACL: only web ports inbound, ephemeral ports outbound.
  # No explicit deny-all rule: AWS network ACLs are deny-by-default, so a final
  # deny rule adds no security but does confuse scanners and readers.
  public_nacl_ingress = [
    { rule_number = 100, protocol = "tcp", action = "allow", cidr_block = "0.0.0.0/0", from_port = 443, to_port = 443 },
    { rule_number = 110, protocol = "tcp", action = "allow", cidr_block = "0.0.0.0/0", from_port = 80, to_port = 80 },
    { rule_number = 120, protocol = "tcp", action = "allow", cidr_block = "0.0.0.0/0", from_port = 1024, to_port = 65535 },
  ]

  private_nacl_ingress = [
    { rule_number = 100, protocol = "-1", action = "allow", cidr_block = var.vpc_cidr, from_port = 0, to_port = 0 },
  ]

  private_nacl_egress = [
    { rule_number = 100, protocol = "-1", action = "allow", cidr_block = var.vpc_cidr, from_port = 0, to_port = 0 },
    { rule_number = 110, protocol = "tcp", action = "allow", cidr_block = "0.0.0.0/0", from_port = 443, to_port = 443 },
  ]
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = var.enable_dns_support
  enable_dns_hostnames = var.enable_dns_hostnames

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-vpc"
    Tier = "network"
  })
}

# -----------------------------------------------------------------------------
# Subnets - multi-AZ
# -----------------------------------------------------------------------------
resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = local.az_list[count.index % length(local.az_list)]
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name                     = "${var.name_prefix}-public-${local.az_list[count.index % length(local.az_list)]}"
    Tier                     = "public"
    "kubernetes.io/role/elb" = "1"
  })
}

resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.private_subnet_cidrs[count.index]
  availability_zone       = local.az_list[count.index % length(local.az_list)]
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name                              = "${var.name_prefix}-private-${local.az_list[count.index % length(local.az_list)]}"
    Tier                              = "private"
    "kubernetes.io/role/internal-elb" = "1"
  })
}

# -----------------------------------------------------------------------------
# Internet Gateway + public routing (no cost)
# -----------------------------------------------------------------------------
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-igw"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-rt-public"
    Tier = "public"
  })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# -----------------------------------------------------------------------------
# NAT Gateway - OPTIONAL and BILLABLE, disabled by default
# -----------------------------------------------------------------------------
resource "aws_eip" "nat" {
  count = local.nat_count

  domain = "vpc"

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-eip-nat-${count.index + 1}"
  })
}

resource "aws_nat_gateway" "this" {
  count = local.nat_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index % length(aws_subnet.public)].id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-nat-${count.index + 1}"
  })

  depends_on = [aws_internet_gateway.this]
}

# -----------------------------------------------------------------------------
# Private routing - one route table per private subnet
# -----------------------------------------------------------------------------
resource "aws_route_table" "private" {
  count = length(aws_subnet.private)

  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-rt-private-${count.index + 1}"
    Tier = "private"
  })
}

resource "aws_route" "private_nat" {
  count = local.nat_count > 0 ? length(aws_subnet.private) : 0

  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index % local.nat_count].id
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# -----------------------------------------------------------------------------
# Network ACLs - stateless subnet-level guard rails (example, defence in depth)
# -----------------------------------------------------------------------------
resource "aws_network_acl" "public" {
  vpc_id     = aws_vpc.this.id
  subnet_ids = aws_subnet.public[*].id

  dynamic "ingress" {
    for_each = local.public_nacl_ingress
    content {
      rule_no    = ingress.value.rule_number
      protocol   = ingress.value.protocol
      action     = ingress.value.action
      cidr_block = ingress.value.cidr_block
      from_port  = ingress.value.from_port
      to_port    = ingress.value.to_port
    }
  }

  dynamic "egress" {
    for_each = [1]
    content {
      rule_no    = 100
      protocol   = "-1"
      action     = "allow"
      cidr_block = "0.0.0.0/0"
      from_port  = 0
      to_port    = 0
    }
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-nacl-public"
  })
}

resource "aws_network_acl" "private" {
  vpc_id     = aws_vpc.this.id
  subnet_ids = aws_subnet.private[*].id

  dynamic "ingress" {
    for_each = local.private_nacl_ingress
    content {
      rule_no    = ingress.value.rule_number
      protocol   = ingress.value.protocol
      action     = ingress.value.action
      cidr_block = ingress.value.cidr_block
      from_port  = ingress.value.from_port
      to_port    = ingress.value.to_port
    }
  }

  dynamic "egress" {
    for_each = local.private_nacl_egress
    content {
      rule_no    = egress.value.rule_number
      protocol   = egress.value.protocol
      action     = egress.value.action
      cidr_block = egress.value.cidr_block
      from_port  = egress.value.from_port
      to_port    = egress.value.to_port
    }
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-nacl-private"
  })
}

# -----------------------------------------------------------------------------
# Security groups - stateful, least privilege, no 0.0.0.0/0 egress on 22/3389
# -----------------------------------------------------------------------------
# The default security group is created by AWS with an allow-any-any rule to
# itself. Nobody creates it on purpose, so the safest state is "no rules at all".
# Terraform removing all rules from it is what this resource does.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-sg-default-deny-all"
    Note = "Locked down: the AWS-created default SG must never carry rules"
  })
}

resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-app"
  description = "Application tier: ingress only from approved CIDRs, egress limited to VPC and HTTPS"
  vpc_id      = aws_vpc.this.id

  dynamic "ingress" {
    for_each = var.allowed_ingress_cidrs
    content {
      description = "Application port from approved CIDR"
      from_port   = var.app_port
      to_port     = var.app_port
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    description = "Internal VPC traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "HTTPS to AWS APIs and package repositories"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-sg-app"
    Tier = "app"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db"
  description = "Data tier: ingress only from the application security group"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Database port from application tier only"
    from_port       = var.db_port
    to_port         = var.db_port
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    description = "Responses back to the VPC only"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-sg-db"
    Tier = "data"
  })
}

# -----------------------------------------------------------------------------
# S3 gateway endpoint - free, removes NAT data-processing cost for S3 traffic
# -----------------------------------------------------------------------------
resource "aws_vpc_endpoint" "s3" {
  count = var.enable_s3_gateway_endpoint ? 1 : 0

  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowS3ReadWriteFromVpc"
        Effect    = "Allow"
        Principal = "*"
        Action    = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource  = ["*"]
      }
    ]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-vpce-s3"
  })
}

# -----------------------------------------------------------------------------
# VPC Flow Logs - OPTIONAL and BILLABLE
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  name              = "/aws/vpc-flow-logs/${var.name_prefix}"
  retention_in_days = var.flow_logs_retention_days

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-flow-logs"
  })
}

data "aws_iam_policy_document" "flow_logs_assume" {
  count = var.enable_flow_logs ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "flow_logs" {
  count = var.enable_flow_logs ? 1 : 0

  name               = "${var.name_prefix}-vpc-flow-logs"
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume[0].json

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-vpc-flow-logs"
  })
}

data "aws_iam_policy_document" "flow_logs_write" {
  count = var.enable_flow_logs ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.flow_logs[0].arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow_logs_write" {
  count = var.enable_flow_logs ? 1 : 0

  name   = "${var.name_prefix}-vpc-flow-logs-write"
  role   = aws_iam_role.flow_logs[0].id
  policy = data.aws_iam_policy_document.flow_logs_write[0].json
}

resource "aws_flow_log" "this" {
  count = var.enable_flow_logs ? 1 : 0

  iam_role_arn    = aws_iam_role.flow_logs[0].arn
  log_destination = aws_cloudwatch_log_group.flow_logs[0].arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.this.id

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-flow-log"
  })
}
