# Module: networking

Reusable multi-AZ VPC module: public/private segmentation, routing, optional NAT,
stateless NACLs, least-privilege security groups, a free S3 gateway endpoint and
optional VPC Flow Logs.

## What it creates

| Resource | Billable | Default |
|---|---|---|
| `aws_vpc` | no | always |
| `aws_subnet` (public + private, one per AZ) | no | always |
| `aws_internet_gateway` + public route table | no | always |
| `aws_security_group` app / db | no | always |
| `aws_network_acl` public / private | no | always |
| `aws_vpc_endpoint` (S3 gateway) | **no** (gateway endpoints are free) | `true` |
| `aws_nat_gateway` + `aws_eip` | **yes** | `enable_nat_gateway = false` |
| `aws_flow_log` + CloudWatch log group | **yes** | `enable_flow_logs = false` |

## IP planning (defaults)

| Block | CIDR | Purpose |
|---|---|---|
| VPC | `10.0.0.0/16` | 65,536 addresses |
| public-a/b/c | `10.0.0.0/20`, `10.0.16.0/20`, `10.0.32.0/20` | ingress tier, 4,091 usable each |
| private-a/b/c | `10.0.128.0/20`, `10.0.144.0/20`, `10.0.160.0/20` | workloads, 4,091 usable each |
| reserved | `10.0.48.0/20` – `10.0.112.0/20` | future tiers (data, inspection, endpoints) |

Keep `/20` boundaries: AWS reserves 5 addresses per subnet, and `/20` gives room
for EKS/ECS IP-per-task models without re-IP later.

## Usage

```hcl
module "networking" {
  source = "../../modules/networking"

  name_prefix        = "eawlz-dev"
  environment        = "dev"
  aws_region         = "us-east-1"
  vpc_cidr           = "10.0.0.0/16"
  availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

  enable_nat_gateway = false # zero-cost mode
  enable_flow_logs   = false # zero-cost mode

  tags = local.common_tags
}
```

## Design decisions

* **No data sources.** AZs come from a variable so `terraform plan` can run
  completely offline for zero-cost validation. Production callers pass the real
  AZ names (or a `data "aws_availability_zones"` block in the environment root).
* **No auto-assigned public IPs.** `map_public_ip_on_launch = false`; public
  subnets exist for load balancers, not for directly reachable instances.
* **Default egress is closed.** The app SG allows only VPC traffic and TCP/443;
  there is no `0.0.0.0/0` all-protocol egress and no SSH ingress. Administrative
  access is via SSM Session Manager (no inbound port 22 anywhere).
* **NAT is a cost decision, not a default.** One NAT per AZ is highly available
  but triples the hourly charge; `single_nat_gateway = true` is the dev default
  and is documented as a single point of failure.
* **S3 gateway endpoint** removes S3 traffic from the NAT path at zero cost.
* **NACLs are example defence-in-depth**, not the primary control: security
  groups are stateful and are the authoritative rule set.
