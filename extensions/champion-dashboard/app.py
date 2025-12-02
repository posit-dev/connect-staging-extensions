"""
OpenTelemetry Dashboard - Point in Time View
A Shiny dashboard for content platform analytics
"""

from shiny import App, ui, render
from posit.connect import Client
from io import BytesIO, TextIOWrapper
import requests
from prometheus_client import parser
from typing import Dict, List, Tuple, Optional
from datetime import datetime


# CSS Styles
DASHBOARD_CSS = """
    body {
        background-color: #f7f6f3;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    .main-container {
        max-width: 1400px;
        margin: 0 auto;
        padding: 32px 20px;
    }
    .header-section {
        background-color: #ffffff;
        padding: 32px;
        border-radius: 12px;
        margin-bottom: 20px;
        border: 1px solid rgba(55, 53, 47, 0.09);
        box-shadow: none;
    }
    .page-title {
        font-size: 40px;
        font-weight: 700;
        margin-bottom: 6px;
        color: #37352f;
        letter-spacing: -0.4px;
        text-align: center;
    }
    .page-subtitle {
        font-size: 14px;
        color: #787774;
        margin-bottom: 0;
        line-height: 1.6;
    }
    .user-stats-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
    }
    .stat-box {
        background-color: #ffffff;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid rgba(55, 53, 47, 0.09);
        text-align: center;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        min-height: 110px;
        box-shadow: none;
        transition: transform 0.1s ease;
    }
    .stat-box:hover {
        transform: translateY(-1px);
    }
    .stat-box-title {
        font-size: 12px;
        font-weight: 500;
        color: #787774;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stat-box-title-large {
        font-size: 14px;
        font-weight: 600;
        color: #37352f;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .stat-box-value {
        font-size: 42px;
        font-weight: 700;
        color: #2383e2;
        margin-bottom: 4px;
        line-height: 1;
    }
    .stat-box-label {
        font-size: 13px;
        color: #787774;
    }
    .stat-card {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .stat-label {
        font-size: 14px;
        color: #787774;
    }
    .stat-value {
        font-size: 24px;
        font-weight: 600;
        color: #37352f;
    }
    .stat-info {
        font-size: 12px;
        color: #9b9a97;
        margin-top: 4px;
    }
    .content-card {
        background-color: #ffffff;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid rgba(55, 53, 47, 0.09);
        margin-bottom: 16px;
        box-shadow: none;
    }
    .card-title {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 18px;
        color: #37352f;
        display: flex;
        align-items: center;
        gap: 8px;
        padding-bottom: 10px;
        border-bottom: 1px solid rgba(55, 53, 47, 0.09);
    }
    .section-grid-4 {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 16px;
    }
    .section-grid-3 {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-bottom: 16px;
    }
    .section-grid-2 {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 16px;
        margin-bottom: 16px;
    }
    .info-row {
        display: flex;
        justify-content: space-between;
        padding: 12px 0;
        border-bottom: 1px solid rgba(55, 53, 47, 0.09);
    }
    .info-row:last-child {
        border-bottom: none;
    }
    .info-label {
        color: #787774;
        font-size: 14px;
    }
    .info-value {
        color: #37352f;
        font-size: 14px;
        font-weight: 500;
    }
    .content-type-item {
        padding: 6px 0;
        font-size: 14px;
        color: #37352f;
    }
    .vulnerability-box {
        background-color: #fef3e2;
        border: 2px solid #f59e0b;
        border-radius: 12px;
        padding: 24px;
        text-align: center;
        box-shadow: none;
    }
    .vulnerability-count {
        font-size: 48px;
        font-weight: 700;
        color: #c2410c;
        margin-bottom: 8px;
        line-height: 1;
    }
    .vulnerability-label {
        font-size: 13px;
        color: #9a3412;
        font-weight: 600;
    }
    .large-number {
        font-size: 64px;
        font-weight: 700;
        color: #37352f;
        text-align: center;
        margin: 20px 0;
        line-height: 1;
    }
    .section-content {
        font-size: 14px;
        line-height: 1.7;
        max-height: 300px;
        overflow-y: auto;
        padding-right: 8px;
    }
    .section-content::-webkit-scrollbar {
        width: 6px;
    }
    .section-content::-webkit-scrollbar-track {
        background: transparent;
    }
    .section-content::-webkit-scrollbar-thumb {
        background: rgba(55, 53, 47, 0.2);
        border-radius: 6px;
    }
    .section-content::-webkit-scrollbar-thumb:hover {
        background: rgba(55, 53, 47, 0.3);
    }
    .bullet-list {
        list-style-type: disc;
        margin-left: 20px;
        padding-left: 0;
        color: #37352f;
    }
    .bullet-list li {
        padding: 6px 0;
        line-height: 1.6;
    }
    .last-update {
        font-size: 12px;
        color: #9b9a97;
        text-align: right;
        padding: 8px 0;
    }
    .integration-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }
    .integration-table th {
        background-color: #f7f6f3;
        color: #37352f;
        font-weight: 600;
        padding: 12px;
        text-align: left;
        border-bottom: 2px solid rgba(55, 53, 47, 0.09);
    }
    .integration-table td {
        padding: 12px;
        color: #37352f;
        border-bottom: 1px solid rgba(55, 53, 47, 0.09);
    }
    .integration-table th:first-child {
        border-right: 2px solid rgba(55, 53, 47, 0.09);
    }
    .integration-table td:first-child {
        font-weight: 500;
        border-right: 1px solid rgba(55, 53, 47, 0.09);
    }
    .integration-table td:not(:first-child) {
        text-align: center;
    }
    .integration-table th:not(:first-child) {
        text-align: center;
    }
"""

def fetch_all_prometheus_metrics(url: str) -> Dict[str, List[Tuple[Dict[str, str], float]]]:
    try:
        response = requests.get(url)
        response.raise_for_status()
        text_fd = TextIOWrapper(BytesIO(response.content), encoding="utf-8")
        metric_families = parser.text_fd_to_metric_families(text_fd)

        metrics = {}
        for family in metric_families:
            metric_data = []
            for sample in family.samples:
                metric_data.append((sample.labels, sample.value))
            metrics[family.name] = metric_data

        return metrics
    except requests.RequestException as e:
        print(f"Error fetching metrics from {url}: {e}")
        return {}
    
def get_user_activity_metrics(metrics: Dict) -> Dict[str, Optional[int]]:
    """Extract user activity metrics (DAU, WAU, MAU, YAU)."""
    users_active = metrics.get('users_active', [])
    result = {'24h': None, '7d': None, '30d': None, '1y': None}
    
    for labels, value in users_active:
        window = labels.get('window')
        if window in result:
            result[window] = int(value)
    
    return result

def get_content_stats(metrics: Dict) -> Dict:
    """Extract content metrics"""
    content_count = metrics.get('content_count', [])

    stats = {
        "total": 0,
        "by_type": {},
        "runtime_versions": {}
    }

    for labels, value in content_count:
        content_type = labels.get('content_type')
        runtime_lang = labels.get('runtime_language')
        runtime_ver = labels.get('runtime_version')

        if not content_type and not runtime_lang:
            stats["total"] = int(value)

        elif content_type and not runtime_lang:
            # Display "Other" instead of "unknown"
            display_type = "Other" if content_type == "unknown" else content_type
            stats["by_type"][display_type] = int(value)

        elif runtime_lang and runtime_ver:
            runtime_key = f"{runtime_lang} {runtime_ver}"
            stats["runtime_versions"][runtime_key] = int(value)

    return stats

def get_integration_metrics(metrics: Dict) -> Dict:
      """Extract OAuth integration metrics.

      Returns a matrix of counts by template and auth type.
      """
      integrations_count = metrics.get('integrations_count', [])

      # Store counts in a nested dict: template -> auth_type -> count
      matrix = {}
      templates = set()
      auth_types = set()

      for labels, value in integrations_count:
          template = labels.get('integration_template')
          auth_type = labels.get('integration_auth_type')
          count = int(value)

          if template and auth_type:
              templates.add(template)
              auth_types.add(auth_type)

              if template not in matrix:
                  matrix[template] = {}
              matrix[template][auth_type] = count

      return {
          'matrix': matrix,
          'templates': sorted(templates),
          'auth_types': sorted(auth_types)
      }

def get_system_info(client):
    """Get system information"""
    system_info = {}

    response = client.get("server_settings")
    settings = response.json()
    system_info['server_settings'] = settings

    license_info = settings.get('license', {})

    # Extract the key fields
    tier = license_info.get('tier', 'N/A')

    # Determine entitlement (Public Access/Unrestricted)
    anonymous_servers = license_info.get('anonymous-servers', False)
    unrestricted_servers = license_info.get('unrestricted-servers', False)

    if unrestricted_servers:
        entitlement = "Unrestricted"
    elif anonymous_servers:
        entitlement = "Public Access"
    else:
        entitlement = "None"

    # Get R installations
    response = client.get("v1/server_settings/r")
    system_info['r_installations'] = response.json().get('installations', [])

    # Get Python installations
    response = client.get("v1/server_settings/python")
    system_info['python_installations'] = response.json().get('installations', [])

    # Get Quarto installations
    response = client.get("v1/server_settings/quarto")
    system_info['quarto_installations'] = response.json().get('installations', [])

    # Get TensorFlow installations
    response = client.get("v1/server_settings/tensorflow")
    system_info['tensorflow_installations'] = response.json().get('installations', [])

    settings = system_info['server_settings']

    # Extract versions using helper function
    def extract_versions(installations):
        """Extract version strings from installation list"""
        versions = [inst.get('version', '') for inst in installations]
        return ", ".join(versions) if versions else "None"

    r_versions_str = extract_versions(system_info['r_installations'])
    python_versions_str = extract_versions(system_info['python_installations'])
    quarto_versions_str = extract_versions(system_info['quarto_installations'])
    tensorflow_versions_str = extract_versions(system_info['tensorflow_installations'])

    return {
        "Product": "Posit Connect",
        "Version": settings.get("version", "Unknown"),
        "Build": settings.get("build", "Unknown"),
        "Execution Type": "Kubernetes" if settings.get("Launcher", {}).get("Kubernetes") else "Local",
        "License Tier": tier,
        "License Entitlement": entitlement,
        "R Versions": r_versions_str,
        "Python Versions": python_versions_str,
        "Quarto Versions": quarto_versions_str,
        "TensorFlow Versions": tensorflow_versions_str
    }

def get_access_control_stats():
    """Get content access control statistics"""
    return {
        "no_login": 200,
        "all_users": 500,
        "specific_users": 300
    }

def get_oauth_stats():
    """Get OAuth integration statistics"""
    return {
        "Connect API": 200,
        "Databricks": 100,
        "Snowflake": 150
    }

def get_currently_running():
    """Get currently running stats"""
    return {
        "applications": 10,
        "processes": 20
    }

def get_schedule_stats():
    """Get schedule statistics"""
    return {
        "with_schedule": 200,
        "last_24h_successful": 60,
        "last_24h_failed": 2
    }


def create_stat_box(title, value, title_class="stat-box-title"):
    """Create a standardized stat box component"""
    return ui.div(
        ui.div(title, class_=title_class),
        ui.div(str(value), class_="stat-box-value") if value is not None else None,
        class_="stat-box"
    )

def create_content_card(title, *content):
    """Create a standardized content card component"""
    return ui.div(
        ui.div(title, class_="card-title"),
        *content,
        class_="content-card"
    )

def create_list_item(label, value):
    """Create a single info row item"""
    return ui.div(
        ui.span(label + ": ", style="color: #787774;"),
        ui.span(str(value), style="font-weight: 500;"),
        class_="content-type-item"
    )

def create_key_value_list(items_dict):
    """Create a list of key-value pairs"""
    return [create_list_item(label, value) for label, value in items_dict.items()]

app_ui = ui.page_fluid(
    ui.tags.style(DASHBOARD_CSS),

    ui.div(
        # Header Section
        ui.div(
            ui.div("Posit Connect Metrics Dashboard", class_="page-title"),
            style="margin-bottom: 60px;"
        ),

        # Active User Stats Section
        ui.div(
            ui.div("Active User Stats", class_="card-title"),
            ui.div(
                ui.output_ui("active_user_stats"),
                class_="user-stats-container"
            ),
            class_="content-card"
        ),

        # Content Stats Section
        ui.div(
            ui.output_ui("content_stats_grid"),
            class_="section-grid-3"
        ),

        # Integration Metrics Section
        ui.div(
            ui.div("OAuth Integration Stats", class_="card-title"),
            ui.output_ui("integration_metrics_table"),
            class_="content-card"
        ),

        # Access Control, OAuth, and Currently Running Section
        ui.div(
            ui.output_ui("access_oauth_running_grid"),
            class_="section-grid-3"
        ),

        # Schedule Section
        ui.div(
            ui.output_ui("schedule_grid"),
            class_="section-grid-2"
        ),

        # System Info Panel
        ui.div(
            ui.div("System Info", class_="card-title"),
            ui.output_ui("system_info"),
            class_="content-card"
        ),

        class_="main-container"
    )
)

def server(input, output, session):

    # Track app load time
    load_time = datetime.now()

    # Fetch data once on startup
    metrics = fetch_all_prometheus_metrics("http://localhost:3232/metrics")
    client = Client()

    @output
    @render.ui
    def last_update_timestamp():
        """Render last update timestamp"""
        return ui.div(
            f"Last Updated: {load_time.strftime('%Y-%m-%d %H:%M:%S')}",
            class_="last-update"
        )

    @output
    @render.ui
    def active_user_stats():
        """Render active user statistics"""
        user_metrics = get_user_activity_metrics(metrics)

        return [
            create_stat_box("DAU (24h)", user_metrics.get('24h') or 0),
            create_stat_box("WAU (7d)", user_metrics.get('7d') or 0),
            create_stat_box("MAU (30d)", user_metrics.get('30d') or 0),
            create_stat_box("YAU (1y)", user_metrics.get('1y') or 0)
        ]

    @output
    @render.ui
    def system_info():
        """Render system information"""
        info = get_system_info(client)

        rows = []
        for label, value in info.items():
            rows.append(
                ui.div(
                    ui.span(label, class_="info-label"),
                    ui.span(value, class_="info-value"),
                    class_="info-row"
                )
            )

        return ui.div(*rows)

    @output
    @render.ui
    def content_stats_grid():
        """Render content statistics grid"""
        stats = get_content_stats(metrics)

        # Column 1: Total Content
        col1 = ui.div(
            ui.div(
                ui.div(str(stats["total"]), class_="large-number"),
                ui.div("Total pieces of content", style="text-align: center; color: #787774; font-size: 14px;"),
                style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%;"
            ),
            class_="content-card"
        )

        # Column 2: Content by Type
        type_items = []
        for content_type, count in stats["by_type"].items():
            type_items.append(
                ui.div(
                    ui.span(f"{content_type} :: ", style="color: #787774;"),
                    ui.span(str(count), style="font-weight: 500;"),
                    class_="content-type-item"
                )
            )

        col2 = ui.div(
            ui.div("Content by Type", class_="card-title"),
            ui.div(*type_items, class_="section-content"),
            class_="content-card"
        )

        # Column 3: Runtime Versions
        runtime_items = []
        for runtime, count in stats["runtime_versions"].items():
            runtime_items.append(
                ui.div(
                    ui.span(f"{runtime} :: ", style="color: #787774;"),
                    ui.span(str(count), style="font-weight: 500;"),
                    class_="content-type-item"
                )
            )

        col3 = ui.div(
            ui.div("Content by Runtime Version", class_="card-title"),
            ui.div(*runtime_items, class_="section-content"),
            class_="content-card"
        )

        return [col1, col2, col3]

    @output
    @render.ui
    def integration_metrics_table():
        """Render integration metrics as a table"""
        integration_data = get_integration_metrics(metrics)
        matrix = integration_data['matrix']
        templates = integration_data['templates']
        auth_types = integration_data['auth_types']

        # Build table header (templates as columns)
        header_row = ui.tags.tr(
            ui.tags.th(""),
            *[ui.tags.th(template) for template in templates]
        )

        # Build table rows (auth types as rows)
        table_rows = []
        for auth_type in auth_types:
            cells = [ui.tags.td(auth_type)]
            for template in templates:
                count = matrix.get(template, {}).get(auth_type, 0)
                display_value = "." if count == 0 else str(count)
                cells.append(ui.tags.td(display_value))
            table_rows.append(ui.tags.tr(*cells))

        return ui.tags.table(
            ui.tags.thead(header_row),
            ui.tags.tbody(*table_rows),
            class_="integration-table"
        )

    @output
    @render.ui
    def access_oauth_running_grid():
        """Render access control, OAuth, and currently running stats"""
        access_stats = get_access_control_stats()
        oauth_stats = get_oauth_stats()
        running_stats = get_currently_running()

        # Column 1: Access Control
        access_items = {
            "No login required": access_stats["no_login"],
            "All users - login required": access_stats["all_users"],
            "Specific users/groups": access_stats["specific_users"]
        }
        col1 = create_content_card(
            "Content Access Control",
            ui.div(*create_key_value_list(access_items), class_="section-content")
        )

        # Column 2: OAuth Integration
        col2 = create_content_card(
            "OAuth Integration Usage",
            ui.div(*create_key_value_list(oauth_stats), class_="section-content")
        )

        # Column 3: Currently Running
        col3 = create_content_card(
            "Currently Running",
            ui.div(*create_key_value_list(running_stats), class_="section-content")
        )

        return [col1, col2, col3]

    @output
    @render.ui
    def schedule_grid():
        """Render schedule statistics"""
        stats = get_schedule_stats()

        # Column 1: With Schedule
        col1 = ui.div(
            ui.div("Scheduled Content", class_="card-title"),
            ui.div(
                ui.div(str(stats["with_schedule"]), class_="large-number"),
                ui.div(
                    "Pieces of content with schedule",
                    style="text-align: center; color: #787774; font-size: 14px;"
                )
            ),
            class_="content-card"
        )

        # Column 2: Last 24 Hours
        col2 = ui.div(
            ui.div("Last 24 Hours", class_="card-title"),
            ui.div(
                ui.tags.ul(
                    ui.tags.li(f"Successful runs: {stats['last_24h_successful']}"),
                    ui.tags.li(f"Failed runs: {stats['last_24h_failed']}"),
                    class_="bullet-list"
                ),
                class_="section-content"
            ),
            class_="content-card"
        )

        return [col1, col2]

app = App(app_ui, server)
