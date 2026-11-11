# AWS source catalogue

40 official AWS reference cards. Version: `2026-11-10.1+2026-11-10.1+2026-10-14.2`.

Full guidance: `patterns.json` and `aws-patterns.json`. Dates are review dates, not publication dates. Historical entries teach topology only. See [the pipeline and maintenance guide](README.md).

| ID | Reference | Area | Reviewed | Historical |
|---|---|---|---|---|
| `approved-it-remediation` | [Approval-gated operational remediation](https://docs.aws.amazon.com/systems-manager/latest/userguide/running-automations-require-approvals.html) | application | 2026-11-10 | No |
| `serverless-web-api` | [Browser workbench and serverless API](https://docs.aws.amazon.com/whitepapers/latest/serverless-multi-tier-architectures-api-gateway-lambda/single-page-application.html) | application | 2026-11-10 | Yes |
| `container-compute-choice` | [Container orchestration and compute choice](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/choosing-aws-container-service.html) | application | 2026-11-10 | No |
| `durable-workflow-review` | [Durable jobs and human approval](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html) | application | 2026-11-10 | No |
| `messaging-choice` | [Queues, notifications and event routing](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/sns-or-sqs-or-eventbridge.html) | application | 2026-11-10 | No |
| `saas-tenant-isolation` | [Tenant-aware shared and dedicated resources](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html) | application | 2026-11-10 | No |
| `hybrid-network` | [Connectivity between customer networks and AWS](https://docs.aws.amazon.com/whitepapers/latest/aws-vpc-connectivity-options/network-to-amazon-vpc-connectivity-options.html) | cloud | 2026-11-10 | No |
| `database-migration` | [Database replatforming and change capture](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-database-rehost-tools/dms.html) | cloud | 2026-11-10 | No |
| `file-media-transfer` | [File and media migration](https://docs.aws.amazon.com/datasync/latest/userguide/how-datasync-transfer-works.html) | cloud | 2026-11-10 | No |
| `private-storage-access` | [Private access to regional storage services](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html) | cloud | 2026-11-10 | No |
| `private-web-workload` | [Private application behind a load balancer](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-example-private-subnets-nat.html) | cloud | 2026-11-10 | No |
| `rds-failover` | [RDS Multi-AZ availability versus read scaling](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html) | cloud | 2026-11-10 | No |
| `disaster-recovery-strategy` | [Recovery selected by business objectives](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html) | cloud | 2026-11-10 | No |
| `governed-data-lake` | [Governed data producers and consumers](https://docs.aws.amazon.com/prescriptive-guidance/latest/data-lake-for-growth-scale/reference-architecture-components.html) | data | 2026-11-10 | No |
| `database-access-patterns` | [Persistence chosen by data and access patterns](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/databases-on-aws-how-to-choose.html) | data | 2026-11-10 | No |
| `batch-compute` | [Queued compute-intensive batch jobs](https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html) | data | 2026-11-10 | No |
| `stream-processing` | [Streaming ingestion and independent consumers](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html) | data | 2026-11-10 | No |
| `cost-budget-controls` | [Cost tracking and budget notifications](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html) | operations | 2026-11-10 | No |
| `application-identity` | [Application users and federated identity](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools.html) | security | 2026-11-10 | No |
| `security-account-foundation` | [Security ownership and shared controls](https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/architecture.html) | security | 2026-11-10 | No |
| `async-documents` | [Asynchronous document extraction](https://docs.aws.amazon.com/textract/latest/dg/api-async.html) | specialist | 2026-11-10 | No |
| `async-jobs` | [Asynchronous job workers](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/autoscaling-async-job-queues/autoscaling-async-job-queues.html) | specialist | 2026-10-12 | Yes |
| `logging` | [Centralized log analytics](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/centralized-log-analytics/centralized-log-analytics.html) | specialist | 2026-10-12 | Yes |
| `container-ingress` | [Container application ingress](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/networking-inbound.html) | specialist | 2026-10-12 | No |
| `iot-telemetry` | [Device telemetry ingestion](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/connected-home-telemetry/connected-home-telemetry.html) | specialist | 2026-10-12 | Yes |
| `document-speech` | [Document to speech](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/readforme/readforme.html) | specialist | 2026-10-12 | Yes |
| `external-callback` | [External asynchronous API callback](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/invoking-async-external-apis/invoking-async-external-apis.html) | specialist | 2026-10-12 | Yes |
| `graphql-backend` | [GraphQL application backend](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/modern-serverless-mobile-web/modern-serverless-mobile-web.html) | specialist | 2026-10-12 | Yes |
| `knowledge-retrieval` | [Grounded knowledge retrieval](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/grounding-and-rag.html) | specialist | 2026-11-10 | No |
| `hybrid-files` | [Hybrid and partner file ingestion](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/life-sciences-data-collection-storage-processing/life-sciences-data-collection-storage-processing.html) | specialist | 2026-10-12 | Yes |
| `content-moderation` | [Media content moderation](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/content-moderation-compliance/content-moderation-compliance.html) | specialist | 2026-10-12 | Yes |
| `parallel-composition` | [Parallel API composition](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/parallel-api-composition/parallel-api-composition.html) | specialist | 2026-10-12 | Yes |
| `multi-model` | [Parallel model inference](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/multi-model-inference-orchestration/multi-model-inference-orchestration.html) | specialist | 2026-10-12 | Yes |
| `edge-origin` | [Protected external origin](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/securing-custom-origins-waf/securing-custom-origins-waf.html) | specialist | 2026-10-12 | Yes |
| `realtime-bff` | [Real-time backend for frontend](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/backend-for-frontend-api-gateway/backend-for-frontend-api-gateway.html) | specialist | 2026-10-12 | Yes |
| `audio-insights` | [Recorded audio processing](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/ai-audio-insight-pipeline/ai-audio-insight-pipeline.html) | specialist | 2026-10-12 | Yes |
| `search-backed` | [Search-backed application](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/search-backed-applications/search-backed-applications.html) | specialist | 2026-10-12 | Yes |
| `contact-centre` | [Selected AWS contact centre](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/retail-customer-service-contact-center/retail-customer-service-contact-center.html) | specialist | 2026-10-12 | Yes |
| `agent-runtime` | [Tool-using agent runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html) | specialist | 2026-10-12 | No |
| `transactional-outbox` | [Transactional events](https://docs.aws.amazon.com/reference-architecture-diagrams/latest/domain-consistency-event-driven/domain-consistency-event-driven.html) | specialist | 2026-10-12 | Yes |
