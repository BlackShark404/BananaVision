---
name: discovering-gcp-data-assets
description: "Finds and inspects data assets within Google Cloud. Relevant when any of the following conditions are true: 1. The user request involves finding, exploring, or inspecting data assets in Google Cloud, such as: - BigQuery datasets, tables, or views - BigLake catalog or tables - Spanner instances, databases or tables - etc. 2. You need to retrieve the schema, metadata, or governance policies for a GCP data asset. 3. You have a keyword or topic (e.g., \"sales data\") but lack the specific table or resource ID. 4. You are attempting to find data using `bq ls`, as this skill offers a superior approach. Don't use when: - Assets are outside Google Cloud"
version: 1.0.0
---

# Activate Skill: discovering-gcp-data-assets

Please read and internalize the skill documentation located at:
**`C:/Users/Roronoa Zoro/.gemini/skills/discovering-gcp-data-assets/SKILL.md`**

(And any other relevant files in that directory)

## Mission
Finds and inspects data assets within Google Cloud. Relevant when any of the following conditions are true: 1. The user request involves finding, exploring, or inspecting data assets in Google Cloud, such as: - BigQuery datasets, tables, or views - BigLake catalog or tables - Spanner instances, databases or tables - etc. 2. You need to retrieve the schema, metadata, or governance policies for a GCP data asset. 3. You have a keyword or topic (e.g., "sales data") but lack the specific table or resource ID. 4. You are attempting to find data using `bq ls`, as this skill offers a superior approach. Don't use when: - Assets are outside Google Cloud

## Instructions
1.  **Load Context**: Read the file path provided above.
2.  **Activate Persona**: Adopt the role and expertise defined in that document.
3.  **Execute**: Await further user instructions acting as this expert.
