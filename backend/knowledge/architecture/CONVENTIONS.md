# Reviewed diagram conventions — aws-reference-light-v1

Reviewed 14 October 2026 against all ten PNGs in `Sample arch diagrams.zip` and
the AWS sources below. The visual palette is a consistent house style informed by
these examples and bundled AWS assets, not an AWS requirement for every diagram.

## Visual hierarchy

| Container | Border | Fill | Badge |
|---|---|---|---|
| AWS Cloud | Solid dark #232F3E | White | Official cloud group glyph |
| Account, when represented | Solid pink #E7157B | White | Official account glyph |
| Region | Dashed teal/green #00A4A6 | White | Official region glyph |
| VPC | Solid purple #8C4FFF | White | Official VPC glyph |
| Availability Zone, when known | Dashed blue #147EBA | White | Label, not a service icon |
| Public subnet | Solid olive #7AA116 | Pale green #F2F6E8 | Official public-subnet glyph |
| Private/isolated subnet | Solid teal #00A4A6 | Pale cyan #E6F6F7 | Official private-subnet glyph plus explicit label |
| Functional/control group | Dashed grey #8795A8 | White | Label only |

PNG and editable draw.io exports share these styles. Parent boxes enclose children;
labels and badges occupy a reserved top strip. The icon assets retain their original
colours. An isolated subnet is explicitly labelled; colour alone never conveys routing.
The region colour requested as green is the teal/green used in these references.

The drawing hierarchy is Cloud > Account > Region > VPC > AZ > Subnet > Workload.
An account spans regions; this hierarchy groups its regional views. Do not reproduce
the inverted Region > Account arrangement in one source screenshot. Omit unknown AZ
detail rather than invent redundancy. Never allow a subnet to span AZ boundaries.

## Architecture checks before layout

1. Identify category and view: a logical functional band does not prove deployment.
2. Respect current BRD scope and authored solution; no borrowed customers, capacity,
   integrations, account names, region, model choice, HA or excluded components.
3. External actors, SaaS and on-premises systems stay outside AWS. Existing AWS
   resources use their confirmed account, not silently the proposed one.
4. Customer EC2/container/database resources belong in their actual VPC/subnets.
   Regional service APIs such as Bedrock, S3 and DynamoDB stay outside those VPCs.
   A private endpoint does not move its service into the customer subnet.
5. Interface endpoint network interfaces belong in selected subnets. S3/DynamoDB
   gateway endpoints are VPC route-table targets, not subnet-hosted machines.
6. Public/private/isolated are routing properties, not merely colours. Public zonal
   NAT provides outbound internet access; it is not an ingress component. Do not add
   NAT when only private endpoints are needed. IGW attaches to VPC, not subnet.
7. An ALB belongs to one VPC with selected subnet attachments, not between two VPCs.
   Targets may be private. WAF is protection associated with supported ingress,
   not an arbitrary hop in authentication. Do not claim HA from two different services.
8. Distinguish service control plane from worker placement (Batch, ECS, SageMaker,
   AgentCore); resolve the actual hosting/network mode rather than copying a box.
9. Place global services at account level and regional controls inside their region.
   Keep monitoring/security off the main processing chain unless a real transfer
   or invocation is being shown. No decorative arrows between every service.
10. Separate runtime, ingestion and model lifecycle. A model registry is not ECR;
    publishing a container is not the same event as approving model weights.

These checks supplement `CONTAINMENT_RULES`, which is passed to the solution writer,
diagram planner, vision reviewer and placement-repair planner. Deterministic scope
normalization and ELK containment catch some errors; not all architectural validity
can be inferred mechanically from service names or screenshots.

## Readability and connectors

- One main reading direction; group related tiers and use side rails for shared controls.
- Short service/role labels, no paragraphs, no customer-specific prose from examples.
- One meaningful directed relationship per edge; no automatic return arrows.
- Dashed **boundaries** indicate grouping, not asynchronous traffic. Dashed **edges**
  require a stated meaning (control, download, etc.); never infer encryption from dashes.
- Avoid icons straddling boundaries, connectors through labels and unnecessary crossings.
- Use the appropriate abstraction without deleting required dependencies for aesthetics.
- Number only useful flows; numbered boxes do not create a new deployment resource.
- Keep an architecture review for the particular BRD. Reference similarity is not certification.

## Official sources

- [AWS architecture icons](https://aws.amazon.com/architecture/icons/): approved assets,
  third-party library currency and toolkit use. Exact palette above is our house style.
- [VPC subnet documentation](https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html):
  single-AZ subnet containment, routing-based subnet types, example public/private tiers.
- [Gateway endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html):
  S3/DynamoDB access via VPC route tables without requiring IGW/NAT.
- [Interface endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html):
  selected-subnet endpoint interfaces.
- [NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html):
  distinguish connectivity and deployment types; do not generalize zonal public NAT to every mode.
- [Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html):
  VPC/subnet attachment and load-balancer deployment configuration.
