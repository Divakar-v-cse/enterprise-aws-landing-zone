###############################################################################
# EC2 module - hardened application instances
#
# Security posture
#  * IMDSv2 enforced (http_tokens = "required"), hop limit 1 so containers
#    cannot reach the instance metadata service and steal the role credentials.
#  * No public IP, no SSH key pair, no inbound port 22: access is SSM only.
#  * Root volume encrypted, gp3, delete_on_termination = true.
#  * Instance role from the iam module provides temporary credentials.
###############################################################################

locals {
  tags = merge(var.tags, {
    Module      = "ec2"
    Environment = var.environment
    Tier        = "app"
  })

  # Only resolve an AMI at plan time when instances are actually requested.
  lookup_ami = var.ami_id == "" && var.instance_count > 0
}

data "aws_ami" "amazon_linux" {
  count = local.lookup_ami ? 1 : 0

  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_instance" "this" {
  count = var.instance_count

  ami                         = var.ami_id != "" ? var.ami_id : data.aws_ami.amazon_linux[0].id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_ids[count.index % length(var.subnet_ids)]
  vpc_security_group_ids      = var.security_group_ids
  iam_instance_profile        = var.instance_profile_name
  monitoring                  = var.enable_detailed_monitoring
  associate_public_ip_address = false
  ebs_optimized               = true
  user_data_replace_on_change = false

  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    environment    = var.environment
    app_port       = var.app_port
    log_group_name = var.log_group_name
    aws_region     = var.aws_region
  })

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    kms_key_id            = var.kms_key_arn
    delete_on_termination = true
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-app-${count.index + 1}"
  })

  lifecycle {
    precondition {
      condition     = var.ami_id != "" || local.lookup_ami
      error_message = "Provide var.ami_id or set instance_count > 0 so the Amazon Linux AMI can be resolved."
    }

    ignore_changes = [ami]
  }
}

