"""Posit Connect Metrics Dashboard"""

from shiny import App, ui, render, reactive
from posit.connect import Client
from io import BytesIO, TextIOWrapper
import requests
from prometheus_client import parser
from typing import Dict, List, Tuple, Optional

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
    .page-title {
        font-size: 40px;
        font-weight: 700;
        margin-bottom: 6px;
        color: #37352f;
        letter-spacing: -0.4px;
        text-align: center;
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
    .stat-box-clickable {
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
        transition: all 0.1s ease;
        cursor: pointer;
    }
    .stat-box-clickable:hover {
        transform: translateY(-2px);
        box-shadow: 0 2px 8px rgba(55, 53, 47, 0.15);
        border-color: #2383e2;
    }
    .stat-box-title {
        font-size: 12px;
        font-weight: 500;
        color: #787774;
        margin-bottom: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stat-box-value {
        font-size: 42px;
        font-weight: 700;
        color: #2383e2;
        margin-bottom: 4px;
        line-height: 1;
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
    .running-item-clickable {
        padding: 16px 20px;
        font-size: 16px;
        color: #37352f;
        cursor: pointer;
        border-radius: 8px;
        border: 2px solid rgba(55, 53, 47, 0.16);
        background-color: #fafafa;
        transition: all 0.2s ease;
        margin: 8px 0;
        text-align: center;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 8px;
    }
    .running-item-clickable:hover {
        background-color: #ffffff;
        border-color: #2383e2;
        box-shadow: 0 2px 8px rgba(35, 131, 226, 0.15);
        transform: translateY(-1px);
    }
    .running-items-container {
        display: flex;
        flex-direction: column;
        padding: 12px;
        gap: 8px;
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
    .content-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }
    .content-table thead {
        border-bottom: 2px solid rgba(55, 53, 47, 0.09);
    }
    .content-table th {
        color: #787774;
        font-weight: 600;
        padding: 12px 8px;
        text-align: left;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .content-table th:last-child {
        text-align: right;
    }
    .content-table td {
        padding: 10px 8px;
        color: #37352f;
        border-bottom: 1px solid rgba(55, 53, 47, 0.06);
    }
    .content-table td:first-child {
        font-weight: 500;
    }
    .content-table td:last-child {
        text-align: right;
        font-weight: 600;
        color: #2383e2;
    }
    .content-table tbody tr:hover {
        background-color: #f7f6f3;
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
    users_active = metrics.get('users_active', [])
    result = {'24h': None, '7d': None, '30d': None, '1y': None}

    for labels, value in users_active:
        window = labels.get('window')
        if window in result:
            result[window] = int(value)

    return result

def get_content_stats(metrics: Dict) -> Dict:
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
        access_type = labels.get('access_type')

        if not content_type and not runtime_lang and not access_type:
            stats["total"] = int(value)

        if content_type and not runtime_lang and not access_type:
            display_type = "Other" if content_type == "unknown" else content_type
            stats["by_type"][display_type] = int(value)

        if runtime_lang and runtime_ver and not content_type and not access_type:
            runtime_key = f"{runtime_lang} {runtime_ver}"
            stats["runtime_versions"][runtime_key] = int(value)

    return stats

def get_integration_metrics(metrics: Dict) -> Dict:
    integrations_count = metrics.get('integrations_count', [])

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
    response = client.get("server_settings")
    settings = response.json()
    system_info = {'server_settings': settings}

    license_info = settings.get('license', {})
    tier = license_info.get('tier', 'N/A')

    anonymous_servers = license_info.get('anonymous-servers', False)
    unrestricted_servers = license_info.get('unrestricted-servers', False)

    if unrestricted_servers:
        entitlement = "Unrestricted"
    elif anonymous_servers:
        entitlement = "Public Access"
    else:
        entitlement = "None"

    response = client.get("v1/server_settings/r")
    system_info['r_installations'] = response.json().get('installations', [])

    response = client.get("v1/server_settings/python")
    system_info['python_installations'] = response.json().get('installations', [])

    response = client.get("v1/server_settings/quarto")
    system_info['quarto_installations'] = response.json().get('installations', [])

    response = client.get("v1/server_settings/tensorflow")
    system_info['tensorflow_installations'] = response.json().get('installations', [])

    def extract_versions(installations):
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

def get_access_control_stats(metrics: Dict) -> Dict[str, int]:
    content_count = metrics.get('content_count', [])
    result = {}

    label_map = {
        "acl": "Specific users/groups",
        "all": "No login required",
        "logged_in": "All users - login required"
    }

    for labels, value in content_count:
        access_type = labels.get('access_type')
        if access_type:
            display_label = label_map.get(access_type, access_type)
            result[display_label] = int(value)

    return result

def get_currently_running(metrics: Dict) -> Dict[str, int]:
    app_count = get_application_count(metrics)
    process_count = get_process_count_by_tag(metrics)

    return {
        "applications": app_count.get('total', 0),
        "processes": process_count.get('total', 0)
    }

def get_application_count(metrics: Dict) -> Dict:
    application_count = metrics.get('application_count', [])
    result = {
        'total': 0,
        'by_type': {}
    }

    for labels, value in application_count:
        application_type = labels.get('application_type')
        if not application_type:
            result['total'] = int(value)
        else:
            result['by_type'][application_type] = int(value)

    return result

def get_schedule_count_by_type(metrics: Dict) -> Dict[str, int]:
    schedule_count = metrics.get('schedule_count', [])
    result = {}

    for labels, value in schedule_count:
        schedule_type = labels.get('schedule_type')
        if schedule_type:
            result[schedule_type] = int(value)

    return result

def get_process_count_by_tag(metrics: Dict) -> Dict:
    process_count = metrics.get('process_count', [])
    by_tag = {}

    for labels, value in process_count:
        process_tag = labels.get('process_tag')
        if process_tag:
            by_tag[process_tag] = int(value)

    return {
        'total': sum(by_tag.values()) if by_tag else 0,
        'by_tag': by_tag
    }

def create_stat_box(title, value, title_class="stat-box-title"):
    return ui.div(
        ui.div(title, class_=title_class),
        ui.div(str(value), class_="stat-box-value") if value is not None else None,
        class_="stat-box"
    )

def create_content_card(title, *content):
    return ui.div(
        ui.div(title, class_="card-title"),
        *content,
        class_="content-card"
    )

def create_list_item(label, value):
    return ui.div(
        ui.span(label + ": ", style="color: #787774;"),
        ui.span(str(value), style="font-weight: 500;"),
        class_="content-type-item"
    )

def create_key_value_list(items_dict):
    return [create_list_item(label, value) for label, value in items_dict.items()]

app_ui = ui.page_fluid(
    ui.tags.style(DASHBOARD_CSS),
    ui.div(
        ui.div(
            ui.div("Posit Connect Metrics Dashboard", class_="page-title"),
            style="margin-bottom: 60px;"
        ),
        ui.div(
            ui.div("Active User Stats", class_="card-title"),
            ui.div(
                ui.output_ui("active_user_stats"),
                class_="user-stats-container"
            ),
            class_="content-card"
        ),
        ui.div(
            ui.output_ui("content_stats_grid"),
            class_="section-grid-4"
        ),
        ui.div(
            ui.div("OAuth Integration Stats", class_="card-title"),
            ui.output_ui("integration_metrics_table"),
            class_="content-card"
        ),
        ui.div(
            ui.output_ui("running_schedule_grid"),
            class_="section-grid-2"
        ),
        ui.div(
            ui.div("System Info", class_="card-title"),
            ui.output_ui("system_info"),
            class_="content-card"
        ),
        class_="main-container"
    )
)

def server(input, output, session):
    metrics = fetch_all_prometheus_metrics("http://localhost:3232/metrics")
    client = Client()

    @output
    @render.ui
    def active_user_stats():
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
        stats = get_content_stats(metrics)

        col1 = ui.div(
            ui.div(
                ui.div(str(stats["total"]), class_="large-number"),
                ui.div("Total pieces of content", style="text-align: center; color: #787774; font-size: 14px;"),
                style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%;"
            ),
            class_="content-card"
        )

        sorted_types = sorted(stats["by_type"].items(), key=lambda x: x[1], reverse=True)
        type_rows = [
            ui.tags.tr(
                ui.tags.td(content_type),
                ui.tags.td(str(count))
            )
            for content_type, count in sorted_types
        ]

        col2 = ui.div(
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Type"),
                            ui.tags.th("Count")
                        )
                    ),
                    ui.tags.tbody(*type_rows),
                    class_="content-table"
                ),
                class_="section-content"
            ),
            class_="content-card"
        )

        # Define runtime priority order
        runtime_order = {"R": 0, "Python": 1, "Quarto": 2}

        # Custom sorting: first by runtime type, then by count (descending) within each type
        def sort_key(item):
            runtime, count = item
            # Extract the runtime language (first word)
            runtime_lang = runtime.split()[0] if runtime else ""
            # Get priority (default to 999 for unknown runtimes)
            priority = runtime_order.get(runtime_lang, 999)
            # Return tuple: (priority, -count) to sort by priority first, then count descending
            return (priority, -count)

        sorted_runtimes = sorted(stats["runtime_versions"].items(), key=sort_key)
        runtime_rows = [
            ui.tags.tr(
                ui.tags.td(runtime),
                ui.tags.td(str(count))
            )
            for runtime, count in sorted_runtimes
        ]

        col3 = ui.div(
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Runtime Version"),
                            ui.tags.th("Count")
                        )
                    ),
                    ui.tags.tbody(*runtime_rows),
                    class_="content-table"
                ),
                class_="section-content"
            ),
            class_="content-card"
        )

        access_stats = get_access_control_stats(metrics)
        sorted_access_stats = sorted(access_stats.items(), key=lambda x: x[1], reverse=True)
        access_rows = [
            ui.tags.tr(
                ui.tags.td(access_type),
                ui.tags.td(str(count))
            )
            for access_type, count in sorted_access_stats
        ]

        col4 = ui.div(
            ui.div(
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Access Type"),
                            ui.tags.th("Count")
                        )
                    ),
                    ui.tags.tbody(*access_rows),
                    class_="content-table"
                ),
                class_="section-content"
            ),
            class_="content-card"
        )

        return [col1, col2, col3, col4]

    @output
    @render.ui
    def integration_metrics_table():
        integration_data = get_integration_metrics(metrics)
        matrix = integration_data['matrix']
        templates = integration_data['templates']
        auth_types = integration_data['auth_types']

        header_row = ui.tags.tr(
            ui.tags.th(""),
            *[ui.tags.th(template) for template in templates],
            ui.tags.th("Total")
        )

        table_rows = []
        for auth_type in auth_types:
            cells = [ui.tags.td(auth_type)]
            row_total = 0
            for template in templates:
                count = matrix.get(template, {}).get(auth_type, 0)
                row_total += count
                display_value = "." if count == 0 else str(count)
                cells.append(ui.tags.td(display_value))
            cells.append(ui.tags.td(str(row_total)))
            table_rows.append(ui.tags.tr(*cells))

        return ui.tags.table(
            ui.tags.thead(header_row),
            ui.tags.tbody(*table_rows),
            class_="integration-table"
        )

    @output
    @render.ui
    def running_schedule_grid():
        running_stats = get_currently_running(metrics)
        schedule_by_type = get_schedule_count_by_type(metrics)
        total_scheduled = sum(schedule_by_type.values()) if schedule_by_type else 0

        running_items = [
            ui.div(
                ui.span("Applications: ", style="color: #787774; font-weight: 500;"),
                ui.span(str(running_stats["applications"]), style="font-weight: 700; color: #2383e2; font-size: 18px;"),
                class_="running-item-clickable",
                onclick="Shiny.setInputValue('show_app_breakdown', Math.random())"
            ),
            ui.div(
                ui.span("Processes: ", style="color: #787774; font-weight: 500;"),
                ui.span(str(running_stats["processes"]), style="font-weight: 700; color: #2383e2; font-size: 18px;"),
                class_="running-item-clickable",
                onclick="Shiny.setInputValue('show_process_breakdown', Math.random())"
            )
        ]

        col1 = create_content_card(
            "Currently Running",
            ui.div(*running_items, class_="running-items-container")
        )

        col2 = ui.div(
            ui.div("Scheduled Content", class_="card-title"),
            ui.div(
                ui.div(
                    ui.div(str(total_scheduled), class_="large-number"),
                    ui.div(
                        "Click to view breakdown by type",
                        style="text-align: center; color: #787774; font-size: 12px; font-style: italic;"
                    ),
                    class_="stat-box-clickable",
                    onclick="Shiny.setInputValue('show_schedule_breakdown', Math.random())"
                )
            ),
            class_="content-card"
        )

        return [col1, col2]

    @reactive.effect
    @reactive.event(input.show_app_breakdown)
    def show_application_breakdown():
        app_count = get_application_count(metrics)
        sorted_app_count = dict(sorted(app_count['by_type'].items(), key=lambda x: x[1], reverse=True))
        breakdown_items = create_key_value_list(sorted_app_count)

        m = ui.modal(
            ui.div(
                ui.div("Application Breakdown by Type", style="font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #37352f;"),
                ui.div(*breakdown_items, class_="section-content"),
                style="padding: 10px;"
            ),
            title=None,
            easy_close=True,
            footer=None
        )
        ui.modal_show(m)

    @reactive.effect
    @reactive.event(input.show_process_breakdown)
    def show_process_breakdown():
        process_count = get_process_count_by_tag(metrics)
        sorted_process_count = dict(sorted(process_count['by_tag'].items(), key=lambda x: x[1], reverse=True))
        breakdown_items = create_key_value_list(sorted_process_count)

        m = ui.modal(
            ui.div(
                ui.div("Process Breakdown by Tag", style="font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #37352f;"),
                ui.div(*breakdown_items, class_="section-content"),
                style="padding: 10px;"
            ),
            title=None,
            easy_close=True,
            footer=None
        )
        ui.modal_show(m)

    @reactive.effect
    @reactive.event(input.show_schedule_breakdown)
    def show_schedule_breakdown():
        schedule_by_type = get_schedule_count_by_type(metrics)
        sorted_schedule = dict(sorted(schedule_by_type.items(), key=lambda x: x[1], reverse=True))
        breakdown_items = create_key_value_list(sorted_schedule)

        m = ui.modal(
            ui.div(
                ui.div("Schedule by Type", style="font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #37352f;"),
                ui.div(*breakdown_items, class_="section-content"),
                style="padding: 10px;"
            ),
            title=None,
            easy_close=True,
            footer=None
        )
        ui.modal_show(m)

app = App(app_ui, server)
