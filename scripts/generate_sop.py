import argparse
from pathlib import Path
from datetime import datetime

TEMPLATE = """ID: {id}
TITLE: {title}
SECTION: {section}
URL: {url}

{description}

Conditions:
- {conditions_line1}
- {conditions_line2}
- {conditions_line3}

Trip Criteria:
- {criteria_line1}
- {criteria_line2}
- {criteria_line3}

Operator Actions:
1. {action1}
2. {action2}
3. {action3}
4. {action4}

Notes:
- {note1}
- {note2}
"""

def build_default_fields(args):
    return {
        "id": args.id,
        "title": args.title,
        "section": args.section or "1.0 General",
        "url": args.url or "https://internal.example/sops/" + args.id.lower(),
        "description": args.description or (
            f"This SOP describes how to identify and respond to {args.category.lower()} conditions "
            f"on {args.asset_type} assets."
        ),
        "conditions_line1": "Describe typical loading or operating patterns where this SOP applies.",
        "conditions_line2": "Mention which assets, feeders, buses, or transformers are affected.",
        "conditions_line3": "Mention the kind of signal behavior that indicates the condition.",
        "criteria_line1": "Specify nominal limits and safe operating range (e.g. current, voltage).",
        "criteria_line2": "Define alarm thresholds and durations.",
        "criteria_line3": "Define trip thresholds and durations based on protection settings.",
        "action1": "Verify the condition using SCADA trends or local measurements.",
        "action2": "Confirm that protection device indications match the suspected condition.",
        "action3": "Take corrective action such as rebalancing load or isolating faulty segments.",
        "action4": "Monitor the system after corrective action and escalate to engineering if needed.",
        "note1": "Repeated events under this SOP may indicate a need for system study or upgrades.",
        "note2": "Always follow local safety rules and lockout/tagout procedures.",
    }

def main():
    parser = argparse.ArgumentParser(description="Generate a SOP markdown file for the MAFD KB.")
    parser.add_argument("--id", required=True, help="SOP identifier, e.g. SOP-OVLD-001")
    parser.add_argument("--title", required=True, help="SOP title")
    parser.add_argument("--category", required=True, help="Short category, e.g. Overload, Miscoordination")
    parser.add_argument("--asset-type", default="feeder", help="Asset type, e.g. feeder, transformer, bus")
    parser.add_argument("--section", help="Section reference, e.g. 3.1 Overload Trip Criteria")
    parser.add_argument("--url", help="Optional URL for the SOP")
    parser.add_argument("--description", help="Optional one-paragraph description override")
    parser.add_argument("--slug", help="Optional file slug, e.g. feeder_overload_thermal_protection")
    parser.add_argument("--output-dir", default="data/sop", help="Directory where the SOP file will be written")

    args = parser.parse_args()

    fields = build_default_fields(args)
    content = TEMPLATE.format(**fields)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.slug:
        filename = f"{args.id}_{args.slug}.md"
    else:
        # default slug based on title
        slug = args.title.lower().replace(" ", "_")
        filename = f"{args.id}_{slug}.md"

    output_path = output_dir / filename
    output_path.write_text(content, encoding="utf-8")

    print(f"Generated SOP file: {output_path}")

if __name__ == "__main__":
    main()
