# Public product review

Reviewed November 16, 2026. The supplied URL is a public sales page for a nine-product Pabbly Plus bundle. The page describes Connect as a workflow builder and explicitly advertises MCP-based workflow and integration development. This makes Connect the closest match for the requested automation project. The available evidence covers public product descriptions. No local Pabbly build, package manifest, or exported REA artifact record was supplied. Private implementation, data models, security controls, and runtime behavior are outside the evidence.

| Public evidence | Flowdesk implementation |
| --- | --- |
| The Connect product card advertises multi-step workflows. | An ordered list of filter, set-field, save-record and deliver steps. Each run has a revision and step trace. |
| The card advertises app connections and an integration catalog. | Incoming JSON webhooks and named outbound HTTPS receivers. A receiving service must accept the generated JSON. |
| The card mentions workflow building with MCP. | Eight local stdio tools share the editor’s workflow definitions and run history. |
| Other product cards describe WhatsApp messaging, billing and the rest of the suite. | These are outside this release. |

The source code, UI and database schema are original. Flowdesk is an independent project.

[Public product page, including the Connect card and nine-product overview](https://blackfriday.pabbly.com/)
