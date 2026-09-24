"""
Azure DevOps Backlog Hierarchical Transformer

Transforms raw Azure DevOps flat backlog data into a clean hierarchical structure
showing Epic → Feature → User Story → Task relationships.

Features:
- Loads most recent raw backlog JSON from azure_devops_data/
- Extracts essential fields (title, state, assignee, dates, story points, etc.)
- Builds parent-child hierarchy tree from work item relationships
- Generates statistics by type and state
- Outputs simplified, human-readable JSON with timestamp

Requirements:
- Input files from fetch_dena_backlog.py
- Standard library only (json, pathlib, datetime)

Output: backlog_simplified_YYYYMMDD_HHMMSS.json in azure_devops_data/
"""

import json
from pathlib import Path
from datetime import datetime

def load_latest_backlog_file():
    """Load the most recent backlog JSON file from azure_devops_data/.
    
    Returns:
        dict: JSON data with 'metadata' and 'work_items', or None if no files found
    """
    data_dir = Path(__file__).parent.parent.parent / 'azure_devops_data'
    
    # Find the most recent file
    json_files = list(data_dir.glob('dena_*.json'))
    if not json_files:
        print("✗ No backlog data files found")
        return None
    
    latest_file = max(json_files, key=lambda p: p.stat().st_mtime)
    print(f"Loading: {latest_file.name}")
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_key_fields(work_item):
    """Extract essential fields from a work item.
    
    Args:
        work_item (dict): Raw work item from Azure DevOps API
    
    Returns:
        dict: Simplified item with id, type, title, state, assigned_to, dates,
            and optional fields like story_points, hours, priority, description
    """
    fields = work_item.get('fields', {})
    
    # Get assigned to info
    assigned_to = fields.get('System.AssignedTo', {})
    if isinstance(assigned_to, dict):
        assignee = assigned_to.get('displayName', 'Unassigned')
    else:
        assignee = 'Unassigned'
    
    simple_item = {
        'id': work_item['id'],
        'type': fields.get('System.WorkItemType', 'Unknown'),
        'title': fields.get('System.Title', 'No Title'),
        'state': fields.get('System.State', 'Unknown'),
        'assigned_to': assignee,
        'created_date': fields.get('System.CreatedDate', ''),
        'closed_date': fields.get('Microsoft.VSTS.Common.ClosedDate', ''),
        'priority': fields.get('Microsoft.VSTS.Common.Priority'),
        'value_area': fields.get('Microsoft.VSTS.Common.ValueArea'),
        'moeite_int': fields.get('Custom.MoeiteInt'),
        'area_path': fields.get('System.AreaPath'),
        'business_value': fields.get('Microsoft.VSTS.Common.BusinessValue'),
    }
    
    # Add optional fields if they exist
    if 'System.Description' in fields:
        simple_item['description'] = fields['System.Description']
    
    if 'Microsoft.VSTS.Scheduling.StoryPoints' in fields:
        simple_item['story_points'] = fields['Microsoft.VSTS.Scheduling.StoryPoints']
    
    if 'Custom.Hours' in fields:
        simple_item['hours'] = fields['Custom.Hours']
    
    if 'Custom.ProjectOwner' in fields:
        simple_item['project_owner'] = fields['Custom.ProjectOwner']
    
    # Project area can be stored in two different custom fields
    project_area = fields.get('Custom.Projectarea') or fields.get('Custom.Area')
    if project_area:
        simple_item['project_area'] = project_area
    
    if 'Microsoft.VSTS.Scheduling.StartDate' in fields:
        simple_item['start_date'] = fields['Microsoft.VSTS.Scheduling.StartDate']
    
    if 'Microsoft.VSTS.Scheduling.TargetDate' in fields:
        simple_item['target_date'] = fields['Microsoft.VSTS.Scheduling.TargetDate']
    
    if 'Custom.Completed_Work' in fields:
        simple_item['completed_work'] = fields['Custom.Completed_Work']
    
    return simple_item

def build_hierarchy(work_items):
    """Build hierarchical tree structure from flat work items list.
    
    Args:
        work_items (list): Raw work items with 'id', 'fields', and 'relations'
    
    Returns:
        list: Top-level items (typically Epics) with nested 'children' and 'children_count'
    
    Note:
        Follows 'System.LinkTypes.Hierarchy-Forward' relationships.
        Orphaned items (no parent/children) are excluded.
    """
    # Create a dictionary for quick lookup
    items_by_id = {item['id']: item for item in work_items}
    
    # Create simplified items and build parent-child relationships
    parent_child_map = {}  # parent_id -> [child_ids]
    child_parent_map = {}  # child_id -> parent_id
    
    for item in work_items:
        relations = item.get('relations', [])
        parent_id = item['id']
        
        for relation in relations:
            if relation['rel'] == 'System.LinkTypes.Hierarchy-Forward':
                # This is a child relationship
                child_url = relation['url']
                child_id = int(child_url.split('/')[-1])
                
                if parent_id not in parent_child_map:
                    parent_child_map[parent_id] = []
                parent_child_map[parent_id].append(child_id)
                child_parent_map[child_id] = parent_id
    
    # Find top-level items (items with no parents)
    top_level_items = []
    
    for item in work_items:
        item_id = item['id']
        item_type = item.get('fields', {}).get('System.WorkItemType', '')
        
        # A top-level item has no parent AND is either an Epic or has children.
        # This ensures Epics without children (e.g. leaf Epics) are still included.
        if item_id not in child_parent_map and (item_type == 'Epic' or item_id in parent_child_map):
            top_level_items.append(item_id)
    
    # Build hierarchical structure
    def build_tree(item_id):
        if item_id not in items_by_id:
            return None
        
        item = items_by_id[item_id]
        simple_item = extract_key_fields(item)
        
        # Add children recursively
        if item_id in parent_child_map:
            children = []
            for child_id in parent_child_map[item_id]:
                child_tree = build_tree(child_id)
                if child_tree:
                    children.append(child_tree)
            
            if children:
                simple_item['children'] = children
                simple_item['children_count'] = len(children)
        
        return simple_item
    
    # Build the tree starting from top-level items
    hierarchy = []
    for item_id in sorted(top_level_items):
        tree = build_tree(item_id)
        if tree:
            hierarchy.append(tree)
    
    return hierarchy

def create_summary_stats(work_items, hierarchy):
    """Generate summary statistics for the backlog.
    
    Args:
        work_items (list): All work items
        hierarchy (list): Top-level hierarchy items
    
    Returns:
        dict: Stats with total_work_items, by_type, by_state, and top_level_items counts
    """
    type_counts = {}
    state_counts = {}
    
    for item in work_items:
        fields = item.get('fields', {})
        work_type = fields.get('System.WorkItemType', 'Unknown')
        state = fields.get('System.State', 'Unknown')
        
        type_counts[work_type] = type_counts.get(work_type, 0) + 1
        state_counts[state] = state_counts.get(state, 0) + 1
    
    return {
        'total_work_items': len(work_items),
        'by_type': type_counts,
        'by_state': state_counts,
        'top_level_items': len(hierarchy)
    }

def save_simplified_data(hierarchy, stats, metadata):
    """Save simplified data to date timestamped JSON file.
    
    Args:
        hierarchy (list): Hierarchical work item tree
        stats (dict): Summary statistics
        metadata (dict): Source metadata (organization, fetched_at, total_work_items)
    
    Returns:
        Path: Output file path (backlog_simplified_YYYYMMDD.json)
    """
    output_dir = Path(__file__).parent.parent.parent / 'azure_devops_data'
    output_dir.mkdir(exist_ok=True)
    
    datadate = datetime.now().strftime('%Y%m%d')
    filename = f'backlog_simplified_{datadate}.json'
    output_path = output_dir / filename
    
    output_data = {
        'metadata': {
            'organization': metadata.get('organization'),
            'simplified_at': datetime.now().isoformat(),
            'source_fetched_at': metadata.get('fetched_at'),
            'total_work_items': metadata.get('total_work_items')
        },
        'statistics': stats,
        'backlog': hierarchy
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Simplified data saved to: {output_path}")
    return output_path

def print_hierarchy_preview(hierarchy, max_items=3):
    """Print console preview of hierarchy structure.
    
    Args:
        hierarchy (list): Top-level work item trees
        max_items (int): Max top-level items to display (default: 3)
    """
    print(f"\n{'='*80}")
    print("HIERARCHY PREVIEW (showing first {0} top-level items)".format(max_items))
    print(f"{'='*80}")
    
    def print_item(item, indent=0):
        prefix = "  " * indent
        print(f"\n{prefix}[{item['type']}] {item['title']}")
        print(f"{prefix}  ID: {item['id']} | State: {item['state']} | Assigned: {item['assigned_to']}")
        
        if 'children' in item:
            print(f"{prefix}  └─ {item['children_count']} child item(s)")
    
    for i, item in enumerate(hierarchy[:max_items]):
        print_item(item, 0)
        
        if 'children' in item:
            for child in item['children'][:2]:  # Show first 2 children
                print_item(child, 1)
                
                if 'children' in child:
                    for grandchild in child['children'][:2]:  # Show first 2 grandchildren
                        print_item(grandchild, 2)
            
            if len(item['children']) > 2:
                print(f"    ... and {len(item['children']) - 2} more children")
    
    if len(hierarchy) > max_items:
        print(f"\n... and {len(hierarchy) - max_items} more top-level items")

def main():
    """Orchestrate the simplification process: load, build hierarchy, generate stats, and save."""
    print("="*80)
    print("AZURE DEVOPS BACKLOG DATA SIMPLIFIER")
    print("="*80)
    
    # Load the latest backlog data
    data = load_latest_backlog_file()
    if not data:
        return
    
    metadata = data.get('metadata', {})
    work_items = data.get('work_items', [])
    
    print(f"\n✓ Loaded {len(work_items)} work items")
    
    # Build hierarchical structure
    print("\nBuilding hierarchical structure...")
    hierarchy = build_hierarchy(work_items)
    print(f"✓ Created hierarchy with {len(hierarchy)} top-level items")
    
    # Create statistics
    stats = create_summary_stats(work_items, hierarchy)
    
    print(f"\n{'='*80}")
    print("STATISTICS")
    print(f"{'='*80}")
    print(f"Total work items: {stats['total_work_items']}")
    print(f"\nBy Type:")
    for work_type, count in sorted(stats['by_type'].items()):
        print(f"  - {work_type}: {count}")
    print(f"\nBy State:")
    for state, count in sorted(stats['by_state'].items()):
        print(f"  - {state}: {count}")
    
    # Print preview
    print_hierarchy_preview(hierarchy, max_items=3)
    
    # Save simplified data
    output_path = save_simplified_data(hierarchy, stats, metadata)
    
    print(f"\n{'='*80}")
    print("✓ SIMPLIFICATION COMPLETED")
    print(f"{'='*80}")
    print(f"\nThe simplified JSON file is much easier to read and navigate!")
    print(f"It shows Epics with their Features, User Stories, and Tasks in a tree structure.")

if __name__ == "__main__":
    main()
