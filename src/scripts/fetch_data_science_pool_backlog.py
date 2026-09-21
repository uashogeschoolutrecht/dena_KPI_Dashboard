"""
Azure DevOps Data Science Pool Backlog Fetcher

This script connects to Azure DevOps REST API to fetch all work items from the
Data Science Pool project and saves them to a JSON file for further analysis.

Features:
- Authenticates using Personal Access Token (PAT) from environment variables
- Retrieves all projects from the organization
- Filters for the specific 'Data Science Pool' project
- Fetches all work items using WIQL (Work Item Query Language)
- Implements robust retry logic to handle connection issues
- Saves results to timestamped JSON files with metadata
- Provides detailed progress output and error handling

Requirements:
- Azure DevOps PAT with 'Project and Team: Read' and 'Work Items: Read' permissions
- Environment variable AZURE_API set in .env file
- Dependencies: requests, python-dotenv

Output:
- JSON file in azure_devops_data/ directory with all work items and metadata
- Includes work item details, fields, relationships, and project information
"""

import os
import requests
import json
import base64
import time
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Get API key from environment
AZURE_API_KEY = os.getenv('AZURE_API')

# Azure DevOps configuration
ORGANIZATION = 'HogeschoolUtrecht'
API_VERSION = '7.1'

# Base URL for Azure DevOps REST API (organization level)
BASE_URL = f'https://dev.azure.com/{ORGANIZATION}'

def get_auth_header():
    """Create authentication header using Personal Access Token.
    
    Azure DevOps REST API uses Basic authentication with a PAT.
    The PAT is used as the password with an empty username.
    
    Returns:
        dict: HTTP headers for authentication including:
            - Authorization: Basic auth with base64-encoded credentials
            - Content-Type: application/json for JSON payloads
            - User-Agent: Identifies the client making requests
    
    Raises:
        ValueError: If AZURE_API_KEY is not found in environment variables
    """
    if not AZURE_API_KEY:
        raise ValueError("AZURE_API key not found in .env file")
    
    # Format credentials as ':PAT' (empty username, PAT as password)
    credentials = f':{AZURE_API_KEY}'
    # Base64 encode for Basic authentication
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    return {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/json',
        'User-Agent': 'Python-Azure-DevOps-Client/1.0'
    }

def get_all_projects(max_retries=3):
    """Fetch all projects from the Azure DevOps organization.
    
    Uses the Azure DevOps REST API to retrieve all projects accessible
    with the provided credentials. Implements retry logic with exponential
    backoff to handle transient network issues.
    
    Args:
        max_retries (int): Maximum number of retry attempts (default: 3)
    
    Returns:
        list: List of project dictionaries, each containing:
            - id: Project unique identifier
            - name: Project display name
            - description: Project description (if available)
            - url: API URL for the project
        Returns empty list if all retries fail.
    
    Note:
        Creates a new session for each request to avoid connection pooling
        issues that can occur with persistent connections.
    """
    print("Fetching all projects from Azure DevOps organization...")
    
    url = f'{BASE_URL}/_apis/projects?api-version={API_VERSION}'
    
    print(f"  URL: {url}")
    
    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            
            # Create a new session for each request to avoid connection pooling issues
            # This prevents stale connections and SSL/TLS handshake problems
            session = requests.Session()
            session.headers.update(get_auth_header())
            
            # Disable connection pooling which can cause issues
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=1, 
                pool_maxsize=1,
                max_retries=0
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            
            response = session.get(
                url,
                timeout=30,
                verify=True
            )
            
            session.close()
            
            response.raise_for_status()
            
            projects = response.json()
            print(f"✓ Found {projects['count']} project(s)")
            
            if projects['count'] > 0:
                print("\nProjects found:")
                for project in projects['value']:
                    print(f"  - {project['name']} (ID: {project['id']})")
            
            return projects['value']
            
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 3  # 3, 6, 9 seconds
                print(f"  Connection error, retrying in {wait_time} seconds...")
                print(f"  Error details: {e}")
                time.sleep(wait_time)
            else:
                print(f"✗ Failed to fetch projects after {max_retries} attempts")
                print(f"  Error: {e}")
                print(f"\n  Possible issues:")
                print(f"    - API key might be invalid or expired")
                print(f"    - API key might not have 'Project and Team: Read' permissions")
                print(f"    - Network/firewall blocking the connection")
                print(f"    - Organization name might be incorrect")
                return []
                
        except requests.exceptions.Timeout as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 3
                print(f"  Request timeout, retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"✗ Request timed out after {max_retries} attempts")
                return []
                
        except requests.exceptions.HTTPError as e:
            print(f"✗ HTTP Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"  Status code: {e.response.status_code}")
                print(f"  Response: {e.response.text[:500]}")
                
                if e.response.status_code == 401:
                    print(f"\n  ✗ Authentication failed - API key is invalid or expired")
                elif e.response.status_code == 403:
                    print(f"\n  ✗ Forbidden - API key doesn't have required permissions")
                elif e.response.status_code == 404:
                    print(f"\n  ✗ Not found - Organization name might be incorrect")
            return []
            
        except Exception as e:
            print(f"✗ Unexpected error: {type(e).__name__}: {e}")
            return []
    
    return []

def get_work_items_for_project(project_name, limit=None, max_retries=3):
    """Fetch all work items from a specific Azure DevOps project.
    
    Uses a two-step process:
    1. Execute a WIQL query to get all work item IDs in the project
    2. Fetch detailed information for all work items in batches
    
    Args:
        project_name (str): Name of the Azure DevOps project
        limit (int, optional): Maximum number of work items to fetch. 
            If None, fetches all work items.
        max_retries (int): Maximum retry attempts for API calls (default: 3)
    
    Returns:
        list: List of work item dictionaries with detailed fields including:
            - id: Work item ID
            - fields: Dict of all work item fields (title, state, type, etc.)
            - relations: Links to other work items
            - projectName: Added field with the source project name
        Returns empty list if fetching fails.
    
    Note:
        - Work items are fetched in batches of 50 to balance performance and stability
        - Each batch has its own retry logic
        - Adds 1 second delay between batches to avoid API throttling
    """
    print(f"\n{'='*80}")
    print(f"Fetching work items from project: {project_name}")
    print(f"{'='*80}")
    
    # URL encode the project name to handle spaces and special characters
    project_encoded = quote(project_name)
    
    print("Attempting to fetch work items using simplified API...")
    
    try:
        # Step 1: Use WIQL (Work Item Query Language) to get all work item IDs
        # This is more efficient than trying to get all details at once
        # WIQL allows us to filter by project and get just the IDs first
        
        wiql_url = f'{BASE_URL}/{project_encoded}/_apis/wit/wiql?api-version={API_VERSION}'
        
        # Simple query to get all work item IDs from this project
        # Later we'll fetch full details for these IDs
        query = {
            "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project_name}'"
        }
        
        # Use session management like the working projects call
        for attempt in range(max_retries):
            try:
                print(f"  Attempt {attempt + 1}/{max_retries} - Querying work item IDs...")
                
                # Create a new session
                session = requests.Session()
                session.headers.update(get_auth_header())
                
                # Disable connection pooling
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=1, 
                    pool_maxsize=1,
                    max_retries=0
                )
                session.mount('https://', adapter)
                session.mount('http://', adapter)
                
                # Post WIQL query with timeout
                response = session.post(
                    wiql_url, 
                    json=query,
                    timeout=60
                )
                
                session.close()
                
                response.raise_for_status()
                
                query_results = response.json()
                work_item_ids = [item['id'] for item in query_results.get('workItems', [])]
                
                print(f"✓ Found {len(work_item_ids)} work items in {project_name}")
                break  # Success, exit retry loop
                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Progressive backoff: 2, 4, 6 seconds
                    print(f"  Connection issue, retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    print(f"✗ Failed after {max_retries} attempts")
                    raise
        
        if not work_item_ids:
            print(f"  No work items found in project {project_name}")
            return []
        
        # Apply limit if specified
        if limit:
            work_item_ids = work_item_ids[:limit]
            print(f"  Fetching details for first {len(work_item_ids)} items (limit applied)")
        
        # Step 2: Fetch full work item details in batches
        # The work item details API has a limit, so we batch requests
        # Smaller batch size = more stable but slower, larger = faster but riskier
        all_work_items = []
        batch_size = 50  # Reduced from 100 for better stability
        total_batches = (len(work_item_ids) + batch_size - 1) // batch_size
        
        print(f"  Fetching details in {total_batches} batch(es)...")
        
        for i in range(0, len(work_item_ids), batch_size):
            batch_ids = work_item_ids[i:i + batch_size]
            ids_string = ','.join(map(str, batch_ids))
            batch_num = i // batch_size + 1
            
            # Retry logic for each batch - independent retries for resilience
            for attempt in range(max_retries):
                try:
                    # Get detailed information for the work items
                    # $expand=all includes relations, links, and all available fields
                    details_url = (
                        f'{BASE_URL}/{project_encoded}/_apis/wit/workitems'
                        f'?ids={ids_string}'
                        f'&$expand=all'
                        f'&api-version={API_VERSION}'
                    )
                    
                    print(f"  Fetching batch {batch_num}/{total_batches} ({len(batch_ids)} items)...")
                    
                    # Create a new session for each batch
                    session = requests.Session()
                    session.headers.update(get_auth_header())
                    
                    adapter = requests.adapters.HTTPAdapter(
                        pool_connections=1, 
                        pool_maxsize=1,
                        max_retries=0
                    )
                    session.mount('https://', adapter)
                    session.mount('http://', adapter)
                    
                    response = session.get(
                        details_url,
                        timeout=60
                    )
                    
                    session.close()
                    
                    response.raise_for_status()
                    
                    work_items = response.json()
                    batch_items = work_items.get('value', [])
                    
                    # Add project name to each work item for reference
                    for item in batch_items:
                        item['projectName'] = project_name
                    
                    all_work_items.extend(batch_items)
                    print(f"    ✓ Retrieved {len(batch_items)} items from batch {batch_num}")
                    
                    # Small delay between batches to avoid overwhelming the API
                    if i + batch_size < len(work_item_ids):
                        time.sleep(1)
                    
                    break  # Success, exit retry loop
                    
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"    Connection issue on batch {batch_num}, retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        print(f"    ✗ Failed to fetch batch {batch_num} after {max_retries} attempts")
                        # Continue with other batches instead of failing completely
                        break
        
        print(f"✓ Total retrieved from {project_name}: {len(all_work_items)} work items")
        return all_work_items
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to fetch work items from {project_name}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Response status: {e.response.status_code}")
            print(f"  Response body: {e.response.text[:500]}")  # First 500 chars
        return []
    except Exception as e:
        print(f"✗ Unexpected error for {project_name}: {type(e).__name__}: {e}")
        return []

def get_all_work_items(projects, limit_per_project=None):
    """Fetch work items from multiple projects with aggregated statistics.
    
    Iterates through all provided projects and fetches work items from each.
    Includes delays between projects to avoid API rate limiting.
    
    Args:
        projects (list): List of project dictionaries from get_all_projects()
        limit_per_project (int, optional): Max work items to fetch per project.
            If None, fetches all work items from each project.
    
    Returns:
        tuple: (all_work_items, project_stats) where:
            - all_work_items: Combined list of all work items from all projects
            - project_stats: List of dicts with 'project' name and 'count' of items
    """
    print(f"\n{'='*80}")
    print("FETCHING WORK ITEMS FROM ALL PROJECTS")
    print(f"{'='*80}")
    
    all_work_items = []
    project_stats = []
    
    for idx, project in enumerate(projects):
        project_name = project['name']
        # Fetch work items for this project
        work_items = get_work_items_for_project(project_name, limit=limit_per_project)
        
        if work_items:
            # Aggregate work items from all projects
            all_work_items.extend(work_items)
            # Track statistics per project for reporting
            project_stats.append({
                'project': project_name,
                'count': len(work_items)
            })
        
        # Add delay between projects to avoid API rate limiting (except after last project)
        # Azure DevOps has rate limits, so we space out requests
        if idx < len(projects) - 1:
            print(f"\n  Waiting 2 seconds before next project...")
            time.sleep(2)
    
    print(f"\n{'='*80}")
    print("COLLECTION SUMMARY")
    print(f"{'='*80}")
    print(f"Total projects processed: {len(projects)}")
    print(f"Total work items collected: {len(all_work_items)}")
    print("\nBreakdown by project:")
    for stat in project_stats:
        print(f"  - {stat['project']}: {stat['count']} work items")
    
    return all_work_items, project_stats

def display_work_item_summary(work_items, max_display=10):
    """Display a formatted summary of fetched work items to console.
    
    Shows key information for each work item including ID, type, title,
    state, assignee, and creation date. Limits display to prevent
    overwhelming console output.
    
    Args:
        work_items (list): List of work item dictionaries to display
        max_display (int): Maximum number of items to show (default: 10)
    
    Note:
        If there are more items than max_display, shows a count of remaining items.
    """
    if not work_items:
        print("\nNo work items to display")
        return
    
    print(f"\n{'='*80}")
    print("WORK ITEM SUMMARY (showing first {} items)".format(min(max_display, len(work_items))))
    print(f"{'='*80}")
    
    for item in work_items[:max_display]:
        fields = item.get('fields', {})
        project = item.get('projectName', 'Unknown')
        print(f"\nID: {item['id']} | Project: {project}")
        print(f"  Type: {fields.get('System.WorkItemType', 'N/A')}")
        print(f"  Title: {fields.get('System.Title', 'N/A')}")
        print(f"  State: {fields.get('System.State', 'N/A')}")
        
        # Handle AssignedTo field which can be a dict or missing
        assigned_to = fields.get('System.AssignedTo', {})
        if isinstance(assigned_to, dict):
            assignee = assigned_to.get('displayName', 'Unassigned')
        else:
            assignee = 'Unassigned'
        print(f"  Assigned To: {assignee}")
        print(f"  Created: {fields.get('System.CreatedDate', 'N/A')}")
    
    if len(work_items) > max_display:
        print(f"\n... and {len(work_items) - max_display} more items")

def save_work_items_to_json(work_items, project_stats):
    """Save work items and metadata to a timestamped JSON file.
    
    Creates the azure_devops_data directory if it doesn't exist and saves
    all work items along with collection metadata to a JSON file.
    
    Args:
        work_items (list): List of work item dictionaries to save
        project_stats (list): Statistics about items per project
    
    Output Structure:
        {
            "metadata": {
                "organization": str,
                "fetched_at": ISO timestamp,
                "total_projects": int,
                "total_work_items": int,
                "project_breakdown": [{"project": str, "count": int}, ...]
            },
            "work_items": [work item objects...]
        }
    
    Returns:
        None. Prints the output path and confirmation to console.
    """
    if not work_items:
        print("\nNo work items to save")
        return
    
    # Create output directory in project root
    # Path: DSP_KPI_Dashboard/azure_devops_data/
    output_dir = Path(__file__).parent.parent.parent / 'azure_devops_data'
    output_dir.mkdir(exist_ok=True)
    
    # Generate filename with date
    # Format: data_science_pool_YYYYMMDD.json
    datadate = datetime.now().strftime('%Y%m%d')
    filename = f'data_science_pool_{datadate}.json'
    output_path = output_dir / filename
    
    # Create data structure with metadata
    output_data = {
        'metadata': {
            'organization': ORGANIZATION,
            'fetched_at': datetime.now().isoformat(),
            'total_projects': len(project_stats),
            'total_work_items': len(work_items),
            'project_breakdown': project_stats
        },
        'work_items': work_items
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Data saved to: {output_path}")
    print(f"  Total work items saved: {len(work_items)}")


def main():
    """Main execution function that orchestrates the entire data collection process.
    
    Workflow:
    1. Validates API key is present in environment
    2. Fetches all projects from the Azure DevOps organization
    3. Filters for the 'Data Science Pool' project specifically
    4. Retrieves all work items from that project
    5. Displays a summary of the fetched items
    6. Saves all data to a timestamped JSON file
    
    The script is designed to be run periodically to collect snapshots of
    the Data Science Pool backlog for KPI tracking and analysis.
    
    Returns:
        None. Prints progress and results to console.
    """
    print("="*80)
    print("AZURE DEVOPS BACKLOG DATA FETCHER - DATA SCIENCE POOL")
    print("="*80)
    
    if not AZURE_API_KEY:
        print("\n✗ ERROR: AZURE_API key not found in .env file")
        return
    
    print(f"\n✓ API key loaded from .env file")
    print(f"Organization: {ORGANIZATION}")
    
    # Get all projects
    projects = get_all_projects()
    if not projects:
        print("\n✗ No projects found or failed to fetch projects")
        return
    
    # Filter for the specific project we're interested in
    # You can change this to target a different project
    target_project_name = "Data Science Pool"
    data_science_pool = [p for p in projects if p['name'] == target_project_name]
    
    if not data_science_pool:
        print(f"\n✗ Project '{target_project_name}' not found")
        print("Available projects:")
        for p in projects:
            print(f"  - {p['name']}")
        return
    
    print(f"\n✓ Found project: {target_project_name}")
    print(f"  Project ID: {data_science_pool[0]['id']}")
    
    # Fetch work items from Data Science Pool
    print(f"\nFocusing on: {target_project_name}")
    work_items, project_stats = get_all_work_items(data_science_pool, limit_per_project=None)
    
    if not work_items:
        print(f"\n✗ No work items found in {target_project_name}")
        return
    
    # Display summary
    display_work_item_summary(work_items, max_display=10)
    
    # Save data
    print(f"\n{'='*80}")
    print("SAVING DATA")
    print(f"{'='*80}")
    save_work_items_to_json(work_items, project_stats)
    
    print(f"\n{'='*80}")
    print("✓ SCRIPT COMPLETED SUCCESSFULLY")
    print(f"{'='*80}")
    print(f"\nSummary:")
    print(f"  - Project: {target_project_name}")
    print(f"  - Total work items fetched: {len(work_items)}")
    print(f"  - Data saved to azure_devops_data/ folder")

if __name__ == "__main__":
    main()
