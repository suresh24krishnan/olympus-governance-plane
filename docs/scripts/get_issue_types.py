from olympus.adapters.jira.jira_client import JiraAdapter

jira = JiraAdapter()
project = jira.client.project(jira.project)
print(f"Project: {project.name}")
print("Valid Issue Types are:")
for it in project.issueTypes:
    print(f" - {it.name}")