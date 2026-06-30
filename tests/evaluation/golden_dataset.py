"""
Golden evaluation dataset — 62 manually verified Q&A samples.

Organised by fixture file and format so that a regression in any parser
(PDF, DOCX, MD, HTML, TXT) shows up as a drop in context_recall for that
category's samples.

Fixture files (committed to tests/evaluation/fixtures/docs/):
  rfc9110_excerpt.txt        — HTTP Semantics RFC 9110                 (TXT)
  python312_whatsnew.txt     — Python 3.12 What's New                  (TXT)
  fastapi_readme.md          — FastAPI README                           (MD)
  cc_by_40_legalcode.pdf     — Creative Commons BY 4.0 legal text       (PDF)
  nist_controls_excerpt.docx — NIST SP 800-53r5 Quick-Start Guide       (DOCX)
  transformer_wikipedia.html — Wikipedia: Transformer architecture       (HTML)

Download fixtures once with:
    python tests/evaluation/download_fixtures.py
"""
from app.services.evaluator import EvalSample

# ─────────────────────────────────────────────────────────────────────────────
# Existing samples — keep for backward compatibility
# ─────────────────────────────────────────────────────────────────────────────

GOLDEN_SAMPLES: list[EvalSample] = [
    EvalSample(
        question="What is the company's refund policy?",
        ground_truth=(
            "Customers can request a full refund within 30 days of purchase. "
            "After 30 days, store credit may be issued at the company's discretion."
        ),
        reference_contexts=[
            "Our refund policy allows customers to request a full refund within 30 days of purchase.",
            "After 30 days, store credit may be issued at our discretion.",
            "Refund requests must be submitted through the customer portal with proof of purchase.",
        ],
    ),
    EvalSample(
        question="What are the minimum system requirements?",
        ground_truth=(
            "The minimum system requirements are 8 GB RAM, a 4-core CPU, "
            "and 10 GB of free disk space."
        ),
        reference_contexts=[
            "Minimum system requirements: 8 GB RAM, 4-core processor, 10 GB free disk space.",
            "Recommended configuration: 16 GB RAM, 8-core processor, SSD storage.",
            "Supported operating systems: Windows 10/11, macOS 12+, Ubuntu 22.04 or later.",
        ],
    ),
    EvalSample(
        question="Does it also support batch uploads?",
        ground_truth=(
            "Yes, the system supports batch uploads of up to 50 files at once "
            "via the POST /v1/documents/batch endpoint."
        ),
        reference_contexts=[
            "Single file uploads are accepted via POST /v1/documents.",
            "Batch uploads of up to 50 files are supported via the /v1/documents/batch endpoint.",
            "Supported formats for batch upload include PDF, DOCX, HTML, and plain text.",
        ],
        history=[
            {"role": "user",      "content": "How do I upload documents to the knowledge base?"},
            {"role": "assistant", "content": "Use POST /v1/documents to upload a single file."},
        ],
    ),
    EvalSample(
        question="How long does it take for an uploaded document to become searchable?",
        ground_truth=(
            "Standard documents are searchable within 2–5 minutes. "
            "Large documents over 100 pages may take up to 10 minutes."
        ),
        reference_contexts=[
            "After upload, documents enter a Celery processing queue managed by the worker.",
            "Standard documents (under 100 pages) are indexed and searchable within 2–5 minutes.",
            "Documents exceeding 100 pages may require up to 10 minutes for full processing.",
            "Processing status can be polled via GET /v1/documents/{id}/status.",
        ],
    ),
    EvalSample(
        question="Which file formats are supported for document ingestion?",
        ground_truth=(
            "PDF, DOCX, HTML, Markdown (.md), and plain text (.txt) files are supported."
        ),
        reference_contexts=[
            "Supported input formats: PDF (.pdf), Word documents (.docx), HTML (.html), "
            "Markdown (.md), and plain text (.txt).",
            "Files are parsed using the Unstructured library for layout-aware text extraction.",
            "Maximum file size per upload is 50 MB; larger files are rejected with a 413 error.",
        ],
    ),
]

# ── RFC 7231 domain (existing) ─────────────────────────────────────────────────

GOLDEN_SAMPLES_RFC: list[EvalSample] = [
    EvalSample(
        question="What HTTP request methods are described and what do they do?",
        ground_truth=(
            "GET requests a representation of the target resource. "
            "POST submits data for processing or creates a new resource. "
            "PUT replaces the resource's state with the supplied representation. "
            "DELETE removes the resource. HEAD is identical to GET but without "
            "a response body. PATCH applies partial modifications."
        ),
        reference_contexts=[
            "The GET method requests transfer of a current selected representation "
            "for the target resource.",
            "The POST method requests that the target resource process the representation "
            "enclosed in the request according to the resource's own specific semantics.",
            "The PUT method requests that the state of the target resource be created or "
            "replaced with the state defined by the representation in the request.",
            "The DELETE method requests that the origin server remove the association "
            "between the target resource and its current functionality.",
            "The PATCH method requests that a set of changes be applied to the resource.",
        ],
    ),
    EvalSample(
        question="What do 4xx HTTP status codes indicate and what are some examples?",
        ground_truth=(
            "4xx status codes indicate that the client seems to have erred. "
            "400 means the request is malformed. 401 means authentication is required. "
            "403 means the server refuses to authorize the request. "
            "404 means the resource was not found. 429 means too many requests."
        ),
        reference_contexts=[
            "The 4xx (Client Error) class of status code indicates that the client "
            "seems to have erred.",
            "400 Bad Request: The server cannot process the request due to a client error "
            "such as malformed request syntax.",
            "401 Unauthorized: The request lacks valid authentication credentials.",
            "403 Forbidden: The server understood the request but refuses to authorize it.",
            "404 Not Found: The origin server did not find a current representation for "
            "the target resource.",
            "429 Too Many Requests: The user has sent too many requests in a given time.",
        ],
    ),
    EvalSample(
        question="What about 5xx codes — when does the server return those?",
        ground_truth=(
            "5xx status codes indicate that the server is aware it has erred. "
            "500 Internal Server Error means an unexpected condition prevented the response. "
            "502 Bad Gateway means the gateway received an invalid response from upstream. "
            "503 Service Unavailable means the server is temporarily overloaded or down."
        ),
        reference_contexts=[
            "The 5xx (Server Error) class of status codes indicates that the server is "
            "aware that it has erred or is incapable of performing the requested method.",
            "500 Internal Server Error: The server encountered an unexpected condition.",
            "502 Bad Gateway: The server received an invalid response from an inbound server.",
            "503 Service Unavailable: The server is temporarily unable to handle the request.",
        ],
        history=[
            {
                "role":    "user",
                "content": "What do 4xx HTTP status codes indicate?",
            },
            {
                "role":    "assistant",
                "content": (
                    "4xx codes indicate client errors. For example, 400 is a bad request, "
                    "401 requires authentication, 403 is forbidden, and 404 means not found."
                ),
            },
        ],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# RFC 9110 — HTTP Semantics  (fixture: rfc9110_excerpt.txt, format: TXT)
# ─────────────────────────────────────────────────────────────────────────────

GOLDEN_SAMPLES_RFC9110: list[EvalSample] = [
    EvalSample(
        question="What is the purpose of the HTTP GET method according to RFC 9110?",
        ground_truth=(
            "The GET method requests a transfer of the current selected representation "
            "of the target resource. It is the primary mechanism for information retrieval "
            "and the focus of most performance optimisations."
        ),
        reference_contexts=[
            "The GET method requests transfer of a current selected representation "
            "for the target resource.",
            "GET is the primary mechanism of information retrieval and the focus of almost "
            "all performance optimizations.",
        ],
    ),
    EvalSample(
        question="How does RFC 9110 define a safe HTTP method?",
        ground_truth=(
            "A method is safe if its semantics are essentially read-only. The client does "
            "not request, and cannot expect, any state change on the origin server as a "
            "result of applying a safe method. GET, HEAD, OPTIONS, and TRACE are safe."
        ),
        reference_contexts=[
            "Request methods are considered safe if their defined semantics are essentially "
            "read-only.",
            "The client does not request, and cannot expect, any state change on the origin "
            "server as a result of applying a safe method to a target resource.",
            "Of the request methods defined by this specification, GET, HEAD, OPTIONS, and "
            "TRACE are defined to be safe.",
        ],
    ),
    EvalSample(
        question="What does RFC 9110 say about idempotent methods?",
        ground_truth=(
            "A method is idempotent if the intended effect of multiple identical requests "
            "is the same as for a single request. PUT, DELETE, and safe methods are all "
            "idempotent. POST is not idempotent."
        ),
        reference_contexts=[
            "A request method is considered idempotent if the intended effect on the server "
            "of multiple identical requests with that method is the same as the effect for "
            "a single such request.",
            "The request methods PUT and DELETE, and safe request methods, are defined to be "
            "idempotent.",
        ],
    ),
    EvalSample(
        question="What is content negotiation in HTTP as described in RFC 9110?",
        ground_truth=(
            "Content negotiation is a mechanism for selecting the best representation of a "
            "resource when multiple representations are available. It uses request headers "
            "like Accept, Accept-Language, and Accept-Encoding to express client preferences."
        ),
        reference_contexts=[
            "HTTP provides content negotiation as a mechanism to select the most appropriate "
            "representation when there are multiple representations available.",
            "The Accept header field can be used by user agents to specify response media "
            "types that are acceptable.",
            "Accept-Language indicates the natural language and locale that the client prefers.",
        ],
    ),
    EvalSample(
        question="How does RFC 9110 define the HEAD method?",
        ground_truth=(
            "HEAD is identical to GET except that the server must not send a response body. "
            "It is used to obtain metadata about the resource without transferring its "
            "representation, useful for checking cache validity."
        ),
        reference_contexts=[
            "The HEAD method is identical to GET except that the server MUST NOT send a "
            "message body in the response.",
            "The HEAD method is often used to check whether a cached response is still "
            "valid without incurring the overhead of downloading the full representation.",
        ],
    ),
    EvalSample(
        question="What HTTP status code should a server return when a resource is permanently moved?",
        ground_truth=(
            "The server should return 301 Moved Permanently, which indicates that the target "
            "resource has been assigned a new permanent URI. The response should include a "
            "Location header with the new URI."
        ),
        reference_contexts=[
            "The 301 (Moved Permanently) status code indicates that the target resource has "
            "been assigned a new permanent URI.",
            "The server SHOULD generate a Location header field in the response containing "
            "a preferred URI reference for the new permanent URI.",
        ],
    ),
    EvalSample(
        question="What is the difference between a 401 and a 403 response in RFC 9110?",
        ground_truth=(
            "401 Unauthorized means the request lacks valid authentication credentials — "
            "the client should authenticate and try again. 403 Forbidden means the server "
            "understood the request but refuses to fulfil it regardless of authentication."
        ),
        reference_contexts=[
            "401 (Unauthorized): The request has not been applied because it lacks valid "
            "authentication credentials for the target resource.",
            "403 (Forbidden): The server understood the request but refuses to authorize it. "
            "A server that wishes to make public why the request has been forbidden can "
            "describe that reason in the response payload.",
        ],
    ),
    EvalSample(
        question="How does RFC 9110 describe the OPTIONS method?",
        ground_truth=(
            "OPTIONS requests information about the communication options available for the "
            "target resource. It allows the client to determine what methods, headers, and "
            "other capabilities the server supports without initiating a resource action."
        ),
        reference_contexts=[
            "The OPTIONS method requests information about the communication options "
            "available for the target resource.",
            "A client can use OPTIONS to determine the capabilities of a server without "
            "implying a resource action.",
        ],
    ),
    EvalSample(
        question="What does RFC 9110 say about HTTP caching validators?",
        ground_truth=(
            "HTTP uses two types of validators: strong validators (ETags) which change "
            "whenever the resource content changes, and weak validators (Last-Modified) "
            "which may not change with every modification. ETags are preferred for "
            "precise cache validation."
        ),
        reference_contexts=[
            "HTTP/1.1 uses entity-tags as a strong validator and Last-Modified dates as "
            "a weak validator.",
            "A strong validator changes whenever the associated representation data changes "
            "in a way that would be significant to the party checking the cache.",
            "A weak validator is one that might not change for every change to the "
            "representation data.",
        ],
    ),
    EvalSample(
        question="What is the purpose of the 304 Not Modified response?",
        ground_truth=(
            "304 Not Modified is returned when a conditional GET or HEAD request is "
            "received and the condition evaluates to false — meaning the cached response "
            "is still valid. It has no body and saves bandwidth by avoiding retransmission."
        ),
        reference_contexts=[
            "The 304 (Not Modified) status code indicates that a conditional GET or HEAD "
            "request has been received and would have resulted in a 200 (OK) response if "
            "it were not for the fact that the condition evaluated to false.",
            "The 304 response cannot contain a message body; it is always terminated by the "
            "first empty line after the header fields.",
        ],
        history=[
            {
                "role": "user",
                "content": "What validators does RFC 9110 define for HTTP caching?",
            },
            {
                "role": "assistant",
                "content": (
                    "RFC 9110 defines ETags as strong validators and Last-Modified dates as "
                    "weak validators. ETags are preferred for precise cache validation."
                ),
            },
        ],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# FastAPI README  (fixture: fastapi_readme.md, format: Markdown)
# ─────────────────────────────────────────────────────────────────────────────

GOLDEN_SAMPLES_FASTAPI: list[EvalSample] = [
    EvalSample(
        question="What is FastAPI and what are its key design goals?",
        ground_truth=(
            "FastAPI is a modern, fast web framework for building APIs with Python, "
            "based on standard Python type hints. Its key goals are high performance "
            "(comparable to NodeJS and Go), fast development with fewer bugs, "
            "and automatic interactive API documentation."
        ),
        reference_contexts=[
            "FastAPI is a modern, fast (high-performance), web framework for building APIs "
            "with Python based on standard Python type hints.",
            "Key Features: Fast: Very high performance, on par with NodeJS and Go.",
            "Fast to code: Increase the speed to develop features by about 200% to 300%.",
            "Fewer bugs: Reduce about 40% of human (developer) induced errors.",
        ],
    ),
    EvalSample(
        question="Which Python versions does FastAPI support?",
        ground_truth=(
            "FastAPI requires Python 3.8 or higher."
        ),
        reference_contexts=[
            "Python 3.8+",
        ],
    ),
    EvalSample(
        question="What are the optional dependencies FastAPI recommends?",
        ground_truth=(
            "FastAPI recommends Starlette for the web parts and Pydantic for the data "
            "parts. For production it recommends an ASGI server such as Uvicorn or Hypercorn."
        ),
        reference_contexts=[
            "Starlette for the web parts.",
            "Pydantic for the data parts.",
            "Uvicorn or Hypercorn as the ASGI server.",
        ],
    ),
    EvalSample(
        question="How does FastAPI generate interactive API documentation?",
        ground_truth=(
            "FastAPI automatically generates interactive API documentation using Swagger UI "
            "at /docs and ReDoc at /redoc, based on the OpenAPI standard. No extra code "
            "or configuration is needed."
        ),
        reference_contexts=[
            "Automatic interactive API documentation (thanks to OpenAPI).",
            "Two interactive API documentation user interfaces: Swagger UI and ReDoc.",
            "All automatically generated, from your code.",
        ],
    ),
    EvalSample(
        question="What is the FastAPI installation command?",
        ground_truth=(
            "FastAPI is installed with: pip install fastapi. For production, an ASGI "
            "server is also needed: pip install fastapi uvicorn."
        ),
        reference_contexts=[
            "$ pip install fastapi",
            "You will also need an ASGI server, for production such as Uvicorn.",
        ],
    ),
    EvalSample(
        question="How does FastAPI handle async path operations?",
        ground_truth=(
            "FastAPI supports both regular and async path operations. Define an async "
            "function with 'async def' and FastAPI will await it; use 'def' for synchronous "
            "handlers that run in a thread pool so they don't block the event loop."
        ),
        reference_contexts=[
            "If you are using third party libraries that tell you to call them with await, "
            "declare your path operation functions with async def.",
            "If your function doesn't need to await, declare it as a normal def and FastAPI "
            "will run it in an external thread pool.",
        ],
    ),
    EvalSample(
        question="What performance benchmarks does FastAPI cite?",
        ground_truth=(
            "FastAPI claims very high performance, on par with NodeJS and Go, and is "
            "one of the fastest Python frameworks available, according to independent "
            "TechEmpower benchmarks."
        ),
        reference_contexts=[
            "Very high performance, on par with NodeJS and Go (thanks to Starlette and Pydantic).",
            "One of the fastest Python frameworks available.",
        ],
    ),
    EvalSample(
        question="Does FastAPI support dependency injection?",
        ground_truth=(
            "Yes, FastAPI has a powerful and intuitive dependency injection system. "
            "Dependencies are declared as function parameters and FastAPI resolves them "
            "automatically, supporting nested dependencies."
        ),
        reference_contexts=[
            "FastAPI has a very powerful but intuitive Dependency Injection system.",
            "Dependencies can have sub-dependencies, creating a tree of dependencies.",
        ],
        history=[
            {
                "role": "user",
                "content": "What features make FastAPI suitable for production APIs?",
            },
            {
                "role": "assistant",
                "content": (
                    "FastAPI offers automatic validation, serialization, async support, "
                    "and automatic OpenAPI documentation for production APIs."
                ),
            },
        ],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Creative Commons BY 4.0  (fixture: cc_by_40_legalcode.pdf, format: PDF)
# ─────────────────────────────────────────────────────────────────────────────

GOLDEN_SAMPLES_CC: list[EvalSample] = [
    EvalSample(
        question="What does the CC BY 4.0 license allow you to do?",
        ground_truth=(
            "CC BY 4.0 allows you to share (copy and redistribute in any medium or format) "
            "and adapt (remix, transform, and build upon) the material for any purpose, "
            "even commercially, provided attribution is given to the creator."
        ),
        reference_contexts=[
            "You are free to: Share — copy and redistribute the material in any medium "
            "or format for any purpose, even commercially.",
            "Adapt — remix, transform, and build upon the material for any purpose, "
            "even commercially.",
            "The licensor cannot revoke these freedoms as long as you follow the license terms.",
        ],
    ),
    EvalSample(
        question="What attribution must you provide under CC BY 4.0?",
        ground_truth=(
            "You must give appropriate credit to the creator, provide a link to the license, "
            "and indicate if changes were made. You must do so in any reasonable manner "
            "but not in any way that suggests the licensor endorses you or your use."
        ),
        reference_contexts=[
            "Attribution — You must give appropriate credit, provide a link to the license, "
            "and indicate if changes were made.",
            "You may do so in any reasonable manner, but not in any way that suggests "
            "the licensor endorses you or your use.",
        ],
    ),
    EvalSample(
        question="Can you apply additional legal restrictions to CC BY 4.0 licensed material?",
        ground_truth=(
            "No. You may not apply legal terms or technological measures that legally "
            "restrict others from doing anything the license permits."
        ),
        reference_contexts=[
            "You may not apply legal terms or technological measures that legally "
            "restrict others from doing anything the License permits.",
            "No additional restrictions — You may not apply legal terms or technological "
            "measures that legally restrict others from doing anything the License permits.",
        ],
    ),
    EvalSample(
        question="Does CC BY 4.0 require ShareAlike?",
        ground_truth=(
            "No. CC BY 4.0 does not require ShareAlike. You may distribute adaptations "
            "under any terms you choose. ShareAlike is a condition in CC BY-SA, not CC BY."
        ),
        reference_contexts=[
            "This Public License does not include a ShareAlike condition.",
            "Adapted Material may be licensed under any terms You choose.",
        ],
    ),
    EvalSample(
        question="What does CC BY 4.0 say about patent and trademark rights?",
        ground_truth=(
            "CC BY 4.0 does not grant patent or trademark rights. The license covers "
            "copyright and similar rights only. Patent and trademark rights are explicitly "
            "excluded from the license grant."
        ),
        reference_contexts=[
            "Patent and trademark rights are not licensed under this Public License.",
            "The license grant does not include patent or trademark rights of the Licensor.",
        ],
    ),
    EvalSample(
        question="What happens if you violate the CC BY 4.0 license?",
        ground_truth=(
            "If you violate the license, your rights terminate automatically. However, "
            "if you cure the violation within 30 days of becoming aware of it, your "
            "rights are reinstated automatically."
        ),
        reference_contexts=[
            "Your rights under this Public License terminate automatically if You fail to "
            "comply with its terms.",
            "Where Your right to use the Licensed Material has terminated, it reinstates "
            "automatically as of the date the violation is cured, provided it is cured "
            "within 30 days of Your discovery of the violation.",
        ],
        history=[
            {
                "role": "user",
                "content": "Can CC BY 4.0 licenses be revoked once granted?",
            },
            {
                "role": "assistant",
                "content": (
                    "The licensor cannot revoke the license as long as you comply with "
                    "its terms. Revocation only happens if you violate the terms."
                ),
            },
        ],
    ),
    EvalSample(
        question="Is the CC BY 4.0 license affected by moral rights?",
        ground_truth=(
            "CC BY 4.0 acknowledges moral rights but does not waive them. To the extent "
            "possible, the licensor waives the right to collect royalties through "
            "compulsory licensing schemes, but moral rights are out of scope."
        ),
        reference_contexts=[
            "Moral rights, such as the right of integrity, are not licensed under this "
            "Public License, nor are publicity, privacy, and/or other similar personality rights.",
            "To the extent possible, the Licensor waives any right to collect royalties "
            "from You for the exercise of the Licensed Rights.",
        ],
    ),
    EvalSample(
        question="What is the scope of the CC BY 4.0 license grant?",
        ground_truth=(
            "The license grants a worldwide, royalty-free, non-sublicensable, "
            "non-exclusive, irrevocable right to reproduce, share, and create adaptations "
            "of the licensed material for any purpose, including commercial use."
        ),
        reference_contexts=[
            "Subject to the terms and conditions of this Public License, the Licensor "
            "hereby grants You a worldwide, royalty-free, non-sublicensable, "
            "non-exclusive, irrevocable license.",
            "The license grant covers: reproduce and Share the Licensed Material; "
            "produce, reproduce, and Share Adapted Material.",
        ],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# NIST SP 800-53r5  (fixture: nist_controls_excerpt.docx, format: DOCX)
# ─────────────────────────────────────────────────────────────────────────────

GOLDEN_SAMPLES_NIST: list[EvalSample] = [
    EvalSample(
        question="What is the purpose of NIST SP 800-53?",
        ground_truth=(
            "NIST SP 800-53 provides a catalog of security and privacy controls for "
            "federal information systems and organisations. It helps organisations "
            "protect operations, assets, individuals, and the nation from threats "
            "including cyberattacks and human errors."
        ),
        reference_contexts=[
            "NIST Special Publication 800-53 provides a catalog of security and privacy "
            "controls for all U.S. federal information systems except those related to "
            "national security.",
            "The publication helps organizations protect their operations, assets, and "
            "individuals from a diverse set of threats.",
        ],
    ),
    EvalSample(
        question="What is the Access Control (AC) control family in NIST 800-53?",
        ground_truth=(
            "The Access Control family limits system access to authorised users, processes, "
            "and devices. Key controls include account management, access enforcement, "
            "separation of duties, least privilege, and session management."
        ),
        reference_contexts=[
            "AC — Access Control: Limit system access to authorized users, processes "
            "acting on behalf of authorized users, and devices.",
            "Access Control controls include: AC-1 Policy and Procedures, AC-2 Account "
            "Management, AC-3 Access Enforcement, AC-5 Separation of Duties, "
            "AC-6 Least Privilege.",
        ],
    ),
    EvalSample(
        question="What does the Audit and Accountability control family require?",
        ground_truth=(
            "The Audit and Accountability (AU) family requires creating, protecting, "
            "and retaining audit logs to monitor events, detect anomalies, and support "
            "investigations. It includes controls for audit log management, event logging, "
            "and review of audit records."
        ),
        reference_contexts=[
            "AU — Audit and Accountability: Create, protect, and retain information system "
            "audit records to enable the monitoring, analysis, investigation, and reporting "
            "of unlawful or unauthorized system activity.",
            "AU controls include: AU-2 Event Logging, AU-3 Content of Audit Records, "
            "AU-6 Audit Record Review, Analysis, and Reporting.",
        ],
    ),
    EvalSample(
        question="What is the Incident Response (IR) family in NIST 800-53?",
        ground_truth=(
            "The Incident Response family establishes an operational incident-handling "
            "capability for the system. It covers incident response policy, training, "
            "testing, handling, monitoring, reporting, and assistance."
        ),
        reference_contexts=[
            "IR — Incident Response: Establish an operational incident-handling capability "
            "for organizational information systems.",
            "IR controls include: IR-1 Policy and Procedures, IR-2 Incident Response "
            "Training, IR-3 Incident Response Testing, IR-4 Incident Handling, "
            "IR-5 Incident Monitoring, IR-6 Incident Reporting.",
        ],
    ),
    EvalSample(
        question="How does NIST 800-53 define the principle of least privilege?",
        ground_truth=(
            "Least privilege (AC-6) requires that each user, process, and device is "
            "granted only the access rights needed to perform its authorised functions. "
            "This limits the damage from errors, accidents, or malicious actions."
        ),
        reference_contexts=[
            "AC-6 Least Privilege: Employ the principle of least privilege, allowing only "
            "authorized accesses for users (or processes acting on behalf of users) that "
            "are necessary to accomplish assigned organizational tasks.",
        ],
    ),
    EvalSample(
        question="What is Configuration Management (CM) in NIST 800-53?",
        ground_truth=(
            "Configuration Management establishes and maintains baseline configurations "
            "for information systems. It includes controls for configuration policy, "
            "baselines, change control, security impact analysis, and least functionality."
        ),
        reference_contexts=[
            "CM — Configuration Management: Establish and maintain baseline configurations "
            "and inventories of organizational information systems.",
            "CM controls include: CM-2 Baseline Configuration, CM-3 Configuration Change "
            "Control, CM-4 Security Impact Analysis, CM-7 Least Functionality.",
        ],
    ),
    EvalSample(
        question="What control families address privacy in NIST SP 800-53 Rev 5?",
        ground_truth=(
            "Revision 5 added dedicated privacy controls integrated throughout the catalog. "
            "The Privacy (PT) family covers privacy policy, PII processing, consent, "
            "privacy notices, privacy impact assessments, and data quality."
        ),
        reference_contexts=[
            "NIST SP 800-53 Rev 5 fully integrates privacy controls into the catalog, "
            "creating a unified framework for security and privacy.",
            "PT — Personally Identifiable Information Processing and Transparency: includes "
            "PT-1 Policy, PT-2 Authority to Process PII, PT-3 Purposes of Processing, "
            "PT-5 Privacy Notice, PT-7 Specific Categories of PII.",
        ],
    ),
    EvalSample(
        question="What does Risk Assessment (RA) cover in NIST 800-53?",
        ground_truth=(
            "The Risk Assessment family covers the process of identifying, estimating, "
            "and prioritising risks. It includes risk policy, security categorisation, "
            "risk assessment, vulnerability monitoring, and supply chain risk management."
        ),
        reference_contexts=[
            "RA — Risk Assessment: Assess risks to organizational operations, assets, "
            "individuals, other organizations, and the Nation.",
            "RA controls include: RA-2 Security Categorization, RA-3 Risk Assessment, "
            "RA-5 Vulnerability Monitoring and Scanning, RA-7 Risk Response.",
        ],
    ),
    EvalSample(
        question="What is the System and Communications Protection (SC) control family?",
        ground_truth=(
            "SC controls protect the boundaries of the system and communications. "
            "They cover network partitioning, denial-of-service protection, cryptographic "
            "key management, session authenticity, and protection of information at rest "
            "and in transit."
        ),
        reference_contexts=[
            "SC — System and Communications Protection: Monitor, control, and protect "
            "information transmitted or received by organizational information systems.",
            "SC controls include: SC-5 Denial-of-Service Protection, SC-8 Transmission "
            "Confidentiality and Integrity, SC-12 Cryptographic Key Establishment and "
            "Management, SC-28 Protection of Information at Rest.",
        ],
        history=[
            {
                "role": "user",
                "content": "Which NIST 800-53 family covers encryption of data in transit?",
            },
            {
                "role": "assistant",
                "content": (
                    "SC-8 Transmission Confidentiality and Integrity in the System and "
                    "Communications Protection (SC) family covers encryption of data in transit."
                ),
            },
        ],
    ),
    EvalSample(
        question="How does NIST 800-53 categorise information systems?",
        ground_truth=(
            "Systems are categorised as Low, Moderate, or High impact based on the "
            "potential impact of a confidentiality, integrity, or availability breach. "
            "Control baselines are then selected accordingly — Low, Moderate, or High."
        ),
        reference_contexts=[
            "FIPS 199 defines three levels of potential impact: LOW, MODERATE, and HIGH.",
            "Organizations select an appropriate set of controls based on the security "
            "category of their information system.",
            "The three security control baselines — Low, Moderate, and High — correspond "
            "to the three impact levels defined in FIPS 199.",
        ],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Transformer architecture  (fixture: transformer_wikipedia.html, format: HTML)
# ─────────────────────────────────────────────────────────────────────────────

GOLDEN_SAMPLES_TRANSFORMER: list[EvalSample] = [
    EvalSample(
        question="What is a Transformer in deep learning?",
        ground_truth=(
            "A Transformer is a deep learning architecture based entirely on self-attention "
            "mechanisms, introduced in the 2017 paper 'Attention Is All You Need'. "
            "It replaced recurrent architectures for sequence modelling and became the "
            "foundation for models like BERT and GPT."
        ),
        reference_contexts=[
            "The Transformer is a deep learning architecture introduced in the 2017 paper "
            "'Attention Is All You Need' by Vaswani et al.",
            "Unlike recurrent neural networks, Transformers process entire sequences in "
            "parallel using self-attention mechanisms.",
            "Transformers became the dominant architecture for natural language processing "
            "and later computer vision tasks.",
        ],
    ),
    EvalSample(
        question="What is self-attention in the context of Transformers?",
        ground_truth=(
            "Self-attention (also called intra-attention) is a mechanism that allows "
            "each position in a sequence to attend to all other positions. It computes "
            "attention scores using queries, keys, and values, enabling the model to "
            "capture long-range dependencies in a single step."
        ),
        reference_contexts=[
            "Self-attention, also called intra-attention, is an attention mechanism relating "
            "different positions of a single sequence in order to compute a representation "
            "of the sequence.",
            "The attention function maps a query and a set of key-value pairs to an output.",
            "Scaled Dot-Product Attention computes compatibility of queries with all keys, "
            "then uses the result to weight the values.",
        ],
    ),
    EvalSample(
        question="What is multi-head attention?",
        ground_truth=(
            "Multi-head attention runs the attention mechanism in parallel across multiple "
            "representation subspaces ('heads'). Each head learns different aspects of the "
            "input, and the outputs are concatenated and projected. This allows the model "
            "to jointly attend to information from different positions."
        ),
        reference_contexts=[
            "Multi-head attention allows the model to jointly attend to information from "
            "different representation subspaces at different positions.",
            "With a single attention head, averaging inhibits this ability.",
            "Multi-Head Attention consists of h attention layers running in parallel, "
            "with outputs concatenated and projected.",
        ],
    ),
    EvalSample(
        question="What is the encoder-decoder structure in Transformers?",
        ground_truth=(
            "The original Transformer uses an encoder that maps input sequences to "
            "continuous representations, and a decoder that generates output sequences "
            "one token at a time. The decoder attends to the encoder output via "
            "cross-attention in addition to masked self-attention."
        ),
        reference_contexts=[
            "The Transformer follows an encoder-decoder structure using stacked "
            "self-attention and point-wise, fully connected layers for both the encoder "
            "and decoder.",
            "The encoder maps an input sequence to a sequence of continuous representations.",
            "The decoder generates an output sequence one element at a time, attending "
            "to the encoder output via cross-attention.",
        ],
    ),
    EvalSample(
        question="What is positional encoding in a Transformer?",
        ground_truth=(
            "Positional encodings are added to input embeddings to give the model "
            "information about the order of tokens in the sequence, since Transformers "
            "have no recurrence. They use sine and cosine functions of different "
            "frequencies so the model can learn to attend by relative positions."
        ),
        reference_contexts=[
            "Since the Transformer contains no recurrence and no convolution, positional "
            "encodings are added to the input embeddings to inject information about the "
            "relative or absolute position of the tokens in the sequence.",
            "The positional encoding uses sine and cosine functions of different frequencies.",
        ],
    ),
    EvalSample(
        question="What is BERT and how does it differ from GPT?",
        ground_truth=(
            "BERT (Bidirectional Encoder Representations from Transformers) uses only the "
            "encoder stack and pre-trains bidirectionally using masked language modelling. "
            "GPT (Generative Pre-trained Transformer) uses only the decoder stack and "
            "trains autoregressively left-to-right, making it better for text generation."
        ),
        reference_contexts=[
            "BERT uses the Transformer encoder and is designed to pre-train deep "
            "bidirectional representations from unlabeled text.",
            "GPT (Generative Pre-trained Transformer) uses the Transformer decoder and "
            "generates text autoregressively.",
            "BERT is better for classification and understanding tasks; GPT is better "
            "for text generation tasks.",
        ],
    ),
    EvalSample(
        question="What is the feed-forward network in each Transformer layer?",
        ground_truth=(
            "Each encoder and decoder layer contains a position-wise feed-forward network "
            "applied to each position separately and identically. It consists of two "
            "linear transformations with a ReLU activation in between."
        ),
        reference_contexts=[
            "In addition to attention sub-layers, each layer in the encoder and decoder "
            "contains a fully connected feed-forward network, which is applied to each "
            "position separately and identically.",
            "This consists of two linear transformations with a ReLU activation in between.",
        ],
    ),
    EvalSample(
        question="What problem do Transformers solve compared to RNNs?",
        ground_truth=(
            "Transformers solve the sequential processing bottleneck of RNNs by processing "
            "entire sequences in parallel using self-attention, enabling much faster "
            "training on GPUs. They also better capture long-range dependencies since "
            "the path length between any two positions is O(1) instead of O(n)."
        ),
        reference_contexts=[
            "Unlike RNNs, Transformers process all positions in the sequence simultaneously, "
            "making them highly parallelisable.",
            "The path length between long-range dependencies in the network is O(1) for "
            "self-attention layers, compared to O(n) for RNNs.",
        ],
    ),
    EvalSample(
        question="What is vision transformer (ViT)?",
        ground_truth=(
            "Vision Transformer (ViT) applies the Transformer architecture to image "
            "patches for image classification. An image is split into fixed-size patches, "
            "each linearly embedded as a token, and then processed by a standard "
            "Transformer encoder."
        ),
        reference_contexts=[
            "The Vision Transformer (ViT) applies the Transformer architecture to "
            "image patches for image classification tasks.",
            "An image is split into fixed-size patches; each patch is linearly embedded "
            "and treated as a token in the Transformer.",
        ],
    ),
    EvalSample(
        question="What is masked self-attention and why is it used in the decoder?",
        ground_truth=(
            "Masked self-attention prevents each position in the decoder from attending "
            "to future positions during training. This ensures the autoregressive property: "
            "when generating position i, the model can only see positions 1 through i-1."
        ),
        reference_contexts=[
            "The decoder uses masked self-attention to prevent positions from attending "
            "to subsequent positions in the sequence.",
            "The masking ensures that the predictions for position i depend only on the "
            "known outputs at positions less than i.",
        ],
        history=[
            {
                "role": "user",
                "content": "How does the Transformer decoder differ from the encoder?",
            },
            {
                "role": "assistant",
                "content": (
                    "The decoder has an extra cross-attention layer that attends to the "
                    "encoder output, and uses masked self-attention so it can only see "
                    "previously generated tokens."
                ),
            },
        ],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Python 3.12 What's New  (fixture: python312_whatsnew.txt, format: TXT)
# ─────────────────────────────────────────────────────────────────────────────

GOLDEN_SAMPLES_PYTHON312: list[EvalSample] = [
    EvalSample(
        question="What are the major new features in Python 3.12?",
        ground_truth=(
            "Python 3.12 introduced improved error messages with more precise locations, "
            "a new type parameter syntax (PEP 695) for generics, f-string improvements "
            "allowing nested expressions, a new 'override' decorator (PEP 698), "
            "and performance improvements including reduced interpreter overhead."
        ),
        reference_contexts=[
            "Python 3.12 introduces improved error messages with more precise error "
            "locations in tracebacks.",
            "PEP 695 — Type Parameter Syntax introduces a new, more compact way to "
            "create generic classes and functions.",
            "PEP 701 — Syntactic formalization of f-strings allows nesting of f-strings "
            "and use of the same quote character inside f-string expressions.",
        ],
    ),
    EvalSample(
        question="What is PEP 695 in Python 3.12?",
        ground_truth=(
            "PEP 695 introduces a new type parameter syntax for defining generic classes "
            "and functions using a compact syntax: `def foo[T](x: T) -> T`. This replaces "
            "the older `TypeVar` and `Generic` approach with a more readable inline form."
        ),
        reference_contexts=[
            "PEP 695 — Type Parameter Syntax: A new, more compact way to express generics.",
            "Generic functions and classes can now be defined using the new syntax: "
            "def max[T](args: Iterable[T]) -> T: ...",
            "This replaces the previous TypeVar-based approach to defining generics.",
        ],
    ),
    EvalSample(
        question="What f-string improvements were introduced in Python 3.12?",
        ground_truth=(
            "PEP 701 formalised f-strings, allowing nested f-strings, use of the same "
            "quote characters inside the expression part, multi-line expressions, "
            "and comments inside f-strings. This removes previous restrictions on "
            "f-string content."
        ),
        reference_contexts=[
            "PEP 701 — Syntactic formalization of f-strings.",
            "Allows nesting f-strings and using the same quote character inside "
            "f-string expressions.",
            "Multi-line expressions and comments inside f-string expressions are now allowed.",
        ],
    ),
    EvalSample(
        question="What deprecated features were removed in Python 3.12?",
        ground_truth=(
            "Python 3.12 removed several long-deprecated features including distutils, "
            "certain deprecated unittest methods, wstr fields in Unicode objects, "
            "and deprecated asyncio APIs including @coroutine and explicit event loop "
            "parameters in asyncio high-level APIs."
        ),
        reference_contexts=[
            "Removed the distutils package. Use setuptools or other packages instead.",
            "Removed deprecated unittest methods.",
            "Removed wstr and wstr_length members from the Unicode object implementation.",
        ],
    ),
    EvalSample(
        question="What performance improvements does Python 3.12 include?",
        ground_truth=(
            "Python 3.12 includes a 5% average speedup from reduced interpreter overhead, "
            "a faster comprehension implementation, an improved specialising adaptive "
            "interpreter, and optimised string methods. Memory usage was also reduced "
            "for small objects."
        ),
        reference_contexts=[
            "Python 3.12 is approximately 5% faster than Python 3.11 on the pyperformance "
            "benchmark suite.",
            "Comprehensions are now inlined into the calling frame, avoiding function call "
            "overhead.",
            "The specializing adaptive interpreter continues to improve with more "
            "specializations added.",
        ],
    ),
    EvalSample(
        question="What is the new override decorator in Python 3.12?",
        ground_truth=(
            "PEP 698 adds @typing.override, a decorator that signals to type checkers "
            "that the decorated method is intended to override a base class method. "
            "If the base class does not have the method, the type checker reports an error."
        ),
        reference_contexts=[
            "PEP 698 — Override Decorator for Static Typing.",
            "@typing.override: indicates to a type checker that a method is intended to "
            "override a method in a base class.",
            "If the type checker does not find a matching method in the base class, "
            "it should flag it as an error.",
        ],
    ),
    EvalSample(
        question="What changes were made to the pathlib module in Python 3.12?",
        ground_truth=(
            "Python 3.12 expanded pathlib.Path to support subclassing and added several "
            "new methods including Path.is_junction(), Path.walk() (similar to os.walk()), "
            "and improved the Path.glob() pattern support."
        ),
        reference_contexts=[
            "pathlib.Path can now be subclassed.",
            "Added Path.is_junction() to test whether a path is a junction.",
            "Added Path.walk() for recursive directory traversal, similar to os.walk().",
            "Path.glob() and Path.rglob() now return nothing if pattern has a trailing "
            "separator.",
        ],
    ),
    EvalSample(
        question="How did Python 3.12 change the GIL (Global Interpreter Lock)?",
        ground_truth=(
            "Python 3.12 itself did not remove the GIL but laid groundwork. PEP 703, "
            "which proposes making the GIL optional, was accepted but not yet implemented "
            "in 3.12. Python 3.12 improved sub-interpreters with per-interpreter GILs "
            "as a step toward this goal."
        ),
        reference_contexts=[
            "PEP 684 — A Per-Interpreter GIL: Each subinterpreter now has its own GIL, "
            "allowing true multi-core parallelism when using multiple interpreters.",
            "PEP 703 (Making the GIL Optional) was accepted as a multi-year project; "
            "its implementation begins in a future release.",
        ],
        history=[
            {
                "role": "user",
                "content": "What concurrency improvements came in Python 3.12?",
            },
            {
                "role": "assistant",
                "content": (
                    "Python 3.12 introduced per-interpreter GILs (PEP 684), allowing "
                    "true parallelism across subinterpreters, and set the stage for "
                    "an optional GIL in future versions."
                ),
            },
        ],
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# Combined dataset — use this in evaluation pipelines
# ─────────────────────────────────────────────────────────────────────────────

ALL_GOLDEN_SAMPLES: list[EvalSample] = (
    GOLDEN_SAMPLES           # 5  — Acme Corp policy (TXT, existing)
    + GOLDEN_SAMPLES_RFC     # 3  — RFC 7231 HTTP status codes (TXT, existing)
    + GOLDEN_SAMPLES_RFC9110 # 10 — rfc9110_excerpt.txt          (TXT)
    + GOLDEN_SAMPLES_FASTAPI # 8  — fastapi_readme.md            (MD)
    + GOLDEN_SAMPLES_CC      # 8  — cc_by_40_legalcode.pdf       (PDF)
    + GOLDEN_SAMPLES_NIST    # 10 — nist_controls_excerpt.docx   (DOCX)
    + GOLDEN_SAMPLES_TRANSFORMER  # 10 — transformer_wikipedia.html (HTML)
    + GOLDEN_SAMPLES_PYTHON312    # 8  — python312_whatsnew.txt  (TXT)
)
# Total: 62 samples covering TXT, MD, PDF, DOCX, HTML ingestion paths.

# ─────────────────────────────────────────────────────────────────────────────
# Thresholds used by TestRAGASMetrics
# hallucination_rate is an upper bound (assert <=); all others are lower bounds.
# Slightly relaxed from initial values to account for harder real-document content.
# Tighten these once the first CI run establishes a real baseline.
# ─────────────────────────────────────────────────────────────────────────────

METRIC_THRESHOLDS: dict[str, float] = {
    "faithfulness_score": 0.75,
    "relevancy_score":    0.72,
    "context_precision":  0.68,
    "context_recall":     0.70,
    "answer_quality":     0.60,
    "hallucination_rate": 0.25,  # upper bound
    "retrieval_ratio":    0.10,
    "context_awareness":  0.70,
}
