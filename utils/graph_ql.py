"""
Utility functions for interacting with the Gitcoin GraphQL API.

This module contains functions for constructing dynamic GraphQL queries 
based on configuration files that specify which networks and rounds to fetch 
applications from.

Functions:
    build_dynamic_query(config): Constructs a GraphQL query string from a configuration dict.
    fetch_applications(): Fetches application data from Gitcoin based on configured networks and rounds.
"""

import datetime

import requests

from utils.file_handler import fetch_gitcoin_rounds_by_chain
from utils.utils import sort_key

GITCOIN_GRAPHQL_API_URL = "https://grants-stack-indexer-v2.gitcoin.co/graphql"


def build_dynamic_query(config):
    """
    Constructs a dynamic GraphQL query for fetching application data from the Gitcoin API.

    This function generates a GraphQL query based on the given configuration which includes
    details about networks and specific round IDs to fetch.

    Args:
        config (dict): A dictionary containing network identifiers as keys and details about the rounds and chain IDs as values.
                       Example:
                       {
                           "arbitrum": {
                               "chainId": 42161,
                               "roundIds": ["23", "24", "25"]
                           },
                           "optimism": {
                               "chainId": 10,
                               "roundIds": ["9", "19"]
                           }
                       }

    Returns:
        str: A complete GraphQL query string with embedded network-specific queries and current datetime constraints.
    """
    query_parts = []
    for network, details in config.items():
        rounds_str = ", ".join(f'"{rid}"' for rid in details["roundIds"])
        chain_id = details["chainId"]
        query_part = f"""
        {network}: applications(
            filter: {{
                roundId: {{ in: [{rounds_str}] }}
                chainId: {{ equalTo: {chain_id} }}
                status: {{ equalTo: APPROVED }}
                round: {{
                    donationsStartTime: {{ lessThan: $currentIsoDate }}
                    donationsEndTime: {{ greaterThan: $currentIsoDate }}
                }}
            }}
            first: 1000
            offset: 0
        ) {{
            roundId
            chainId
            project {{
                id
                name
                metadata
                anchorAddress
                registryAddress
            }}
        }}
        """
        query_parts.append(query_part)
    return f"""
    query Applications ($currentIsoDate: Datetime!) {{
        {"".join(query_parts)}
    }}
    """


def fetch_applications():
    """
    Fetches application data from the Gitcoin GraphQL API based on configurations.

    This function first retrieves a configuration dict from an external file handler,
    constructs a dynamic GraphQL query using this configuration,
    and then posts this query to the Gitcoin API. The response is processed to
    combine applications from all specified networks into a single list.

    Returns:
        list: A list of combined application data from all specified networks in the configuration.
        Each entry in the list is a dictionary containing details about the application and associated project.

    Raises:
        requests.exceptions.RequestException: An error occurred during the HTTP request to the Gitcoin GraphQL API.
    """
    config = fetch_gitcoin_rounds_by_chain()
    current_iso_date = datetime.datetime.now().isoformat()
    query = build_dynamic_query(config)
    response = requests.post(
        GITCOIN_GRAPHQL_API_URL,
        json={
            "query": query,
            "operationName": "Applications",
            "variables": {"currentIsoDate": current_iso_date},
        },
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    data = response.json()["data"]
    combined_applications = []
    for network in config.keys():
        combined_applications.extend(data.get(network, []))
    sorted_applications = sorted(
        (
            appl
            for appl in combined_applications
            if appl.get("project")
            and appl["project"].get("metadata")
            and appl["project"]["metadata"].get("projectTwitter")
        ),
        key=sort_key,
    )
    return sorted_applications
