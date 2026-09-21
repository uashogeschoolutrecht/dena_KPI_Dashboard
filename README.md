# D&A Feature Process KPI Dashboard

This repository supports the Data & Analytics (D&A) team in analysing the Feature process in Azure DevOps. It collects Azure DevOps work item data, transforms the backlog into an analysis-friendly structure, and provides a Jupyter notebook for exploring Feature KPIs.

The first use case is the retrospective with the domain teams on 5 October. The analysis covers the period from 20 February 2025, the date of the previous retrospective, through the current date.

> **Status:** Initial setup based on the former Data Science Pool repository. The KPI analysis and D&A project configuration are still being developed.

## Planned Insights

The initial analysis focuses on Features and aims to provide:

- Total number of completed Features.
- Number of completed Features per domain.
- Average effort (`Moeite Int`) per month for completed Features.
- Lead time based on state changes:
  - **Effort determination time:** from `Ingediend` until `Moeite Int` is filled in.
  - **Waiting time:** from `Geprioriteerd` to `In progress`.
  - **Work in progress:** from `In progress` to `Done`.
- Work-in-progress duration analysed:
  - Across all Features.
  - By effort category: `1-2`, `3-5`, and `8+`.
  - Per domain.

Some metrics depend on a reliable Azure DevOps history of state and field changes. In particular, effort determination time may require additional history API work because the current field value alone does not show when `Moeite Int` was entered.

## How It Works

1. **Fetch:** `src/scripts/fetch_data_science_pool_backlog.py` authenticates with an Azure DevOps Personal Access Token and downloads work items through the Azure DevOps REST API.
2. **Transform:** `src/scripts/backlog_hierarchical_transformer.py` converts the raw export into an Epic -> Feature -> User Story -> Task hierarchy and adds summary statistics.
3. **Analyse:** `notebooks/features_analysis.ipynb` loads the transformed data into pandas for filtering and Feature analysis.

The fetch and transform scripts are currently inherited from the DSP repository. Before production use, the Azure DevOps project and output naming in the fetch script must be aligned with the D&A project.

## Project Structure

```
azure_devops_data/  # Fetched backlog data (gitignored)
notebooks/          # Jupyter notebooks for analysis
src/
  scripts/          # Data fetching & processing scripts
```

## Getting Started

1. Create and activate a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `example.env` to `.env` and add an Azure DevOps PAT with *Project and Team: Read* and *Work Items: Read* permissions:
   ```
   cp example.env .env
   ```
   Set the token in `.env`:
   ```
   AZURE_API=your_personal_access_token
   ```
4. Fetch the latest Azure DevOps backlog:
   ```
   python src/scripts/fetch_data_science_pool_backlog.py
   ```
5. Transform the latest export:
   ```
   python src/scripts/backlog_hierarchical_transformer.py
   ```
6. Open the notebook and run its cells to analyse the data:
   ```
   jupyter notebook notebooks/features_analysis.ipynb
   ```

## Data and Security

- Raw exports are written to `azure_devops_data/` and should remain uncommitted.
- Never commit `.env` or expose the Azure DevOps Personal Access Token.
- The notebook and scripts expect the Azure DevOps field names and state names used by the Feature process. Changes in the process configuration may require updates to the analysis.