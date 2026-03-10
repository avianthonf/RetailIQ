import json
import os


def main():
    with open("scan_results.json") as f:
        scan_data = json.load(f)
    with open("schema_results.json") as f:
        schema_data = json.load(f)

    # Simplified Blueprint to Prefix map based on manual scan of app/__init__.py
    bp_prefix_map = {
        "ai_v2": "/api/v2/ai",
        "auth": "/api/v1/auth",
        "i18n": "/api/v1",
        "tax_engine": "/api/v1",
        "payments": "/api/v1",
        "kyc": "/api/v1",
        "einvoicing": "/api/v1",
        "team": "/api/v1/team",
        "store": "/api/v1/store",
        "transactions": "/api/v1/transactions",
        "inventory": "/api/v1/inventory",
        "customers": "/api/v1/customers",
        "analytics": "/api/v1/analytics",
        "forecasting": "/api/v1/forecasting",
        "decisions": "/api/v1/recommendations",
        "nlp": "/api/v1/query",
        "models": "/api/v1/models",
        "receipts": "/api/v1",
        "suppliers": "/api/v1",
        "staff_performance": "/api/v1/staff",
        "offline": "/api/v1/offline",
        "loyalty": "/api/v1",
        "gst": "/api/v1",
        "whatsapp": "/api/v1",
        "chain": "/api/v1/chain",
        "pricing": "/api/v1/pricing",
        "events": "/api/v1",
        "vision": "",
        "market_intelligence": "/api/v2/market",
        "developer": "/api/v1/developer",
        "oauth": "/oauth",
        "api_v2": "/api/v2",
        "finance": "/api/v2/finance",
        "marketplace": "/api/v2/marketplace",
    }

    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "RetailIQ API",
            "version": "1.0.0",
            "description": "Planet-scale retail operations intelligence platform API.",
        },
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
                "OAuth2": {
                    "type": "oauth2",
                    "flows": {
                        "clientCredentials": {
                            "tokenUrl": "/oauth/token",
                            "scopes": {"read:inventory": "Read inventory data", "read:sales": "Read sales data"},
                        }
                    },
                },
            },
        },
    }

    # Add Marshmallow schemas to components
    for name, fields in schema_data.items():
        properties = {}
        required = []
        for f_name, f_info in fields.items():
            properties[f_name] = {"type": f_info["type"]}
            if f_info["required"]:
                required.append(f_name)

        spec["components"]["schemas"][name] = {"type": "object", "properties": properties}
        if required:
            spec["components"]["schemas"][name]["required"] = required

    # Add Standard Response Envelope
    spec["components"]["schemas"]["StandardResponse"] = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "message": {"type": "string"},
            "data": {"type": "object", "nullable": True},
            "error": {"type": "object", "nullable": True},
            "meta": {"type": "object", "nullable": True},
            "timestamp": {"type": "string", "format": "date-time"},
        },
    }

    # Process endpoints
    for ep in scan_data["endpoints"]:
        module = ep["filepath"].split("\\")[0]
        prefix = bp_prefix_map.get(module, "")

        # Special case for some modules like suppliers which have their own suffix in prefix
        # but my map already handles most.
        full_path = (prefix + ep["path"]).replace("//", "/")
        if not full_path:
            full_path = "/"

        if full_path not in spec["paths"]:
            spec["paths"][full_path] = {}

        for method in ep["methods"]:
            method_lower = method.lower()
            op = {
                "summary": ep["doc"].split("\n")[0] if ep["doc"] else ep["fn"],
                "description": ep["doc"],
                "responses": {
                    "200": {
                        "description": "Success",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/StandardResponse"}}},
                    },
                    "422": {"description": "Validation Error"},
                    "401": {"description": "Unauthorized"},
                    "500": {"description": "Internal Server Error"},
                },
            }

            # Add parameters
            if ep["params"]:
                op["parameters"] = []
                # Deduplicate params by name
                seen_params = set()
                for p in ep["params"]:
                    if p["name"] not in seen_params:
                        op["parameters"].append({"name": p["name"], "in": p["in"], "schema": {"type": "string"}})
                        seen_params.add(p["name"])

            # Add request body
            if ep["body_schema"]:
                op["requestBody"] = {
                    "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{ep['body_schema']}"}}}
                }

            # Add security
            if ep["auth"]:
                op["security"] = []
                if "require_auth" in ep["auth"] or "require_role" in ep["auth"]:
                    op["security"].append({"BearerAuth": []})
                if "require_oauth" in ep["auth"]:
                    op["security"].append({"OAuth2": []})

            spec["paths"][full_path][method_lower] = op

    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)


if __name__ == "__main__":
    main()
