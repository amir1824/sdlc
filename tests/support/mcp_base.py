"""The base class and the tool names of the tests of the `mcp` mode (no MCP write in a Jira run).
"""
from support.gate_base import GateTest


UUID_SERVER = "mcp__0dcd0205-81c2-491f-b8e9-2617c355f029__"
NAMED_SERVER = "mcp__atlassian__"
WRITES = ("createJiraIssue", "editJiraIssue", "transitionJiraIssue", "addOrEditJiraIssueComment",
          "createConfluenceContent", "updateConfluenceContent", "showConfluenceEditor", "addGraphContext",
          "executeWrite", "executeDestructive")
READS = ("getJiraIssue", "searchJiraIssuesUsingJql", "listJiraIssueComments", "lookupJiraAccountId",
         "getConfluenceContent", "searchConfluence", "search", "discover", "atlassianUserInfo", "atlassianHome",
         "getAccessibleAtlassianResources", "getGraphContext", "getGraphObject", "getWorkPortfolio", "getPeopleInfo",
         "getCollaborators", "getWorkActivity", "getLoomObjectsContent", "getJiraIssueComment")
LOOKALIKES = ("getOrCreateJiraIssue", "findOrCreateJiraIssue", "searchAndUpdateConfluencePage", "listAndCloseJiraIssues",
              "readThenDeleteJira", "get_jira_and_delete", "discoverAndCreateJiraIssue", "atlassianHomeWriteX",
              "add_graph_context", "execute-write", "execute_destructive", "get_or_set", "list_then_post", "fetchAndPush",
              "search_and_notify", "readThenSubmit", "getAndSetX", "readAndExecute", "fetchAndPost")
OTHER_READS = ("mcp__figma__get_design_context", "mcp__supabase__list_tables", "mcp__Claude_Browser__read_page",
               "mcp__Claude_Browser__get_page_text")
OTHER_WRITES = ("mcp__supabase__execute_sql", "mcp__Claude_Browser__navigate", "mcp__terminal__run_in_terminal",
                "mcp__7eca610e-292a-4260-90ca-1b88681efe7a__generate_image", "mcp__ctx__graphql_mutation_x",
                "mcp__ccd_session__start_session", "mcp__scheduled-tasks__create_scheduled_task")
APP_TOOLS = ("mcp__ccd_turn__update_plan", "mcp__ccd_turn__wrap_up", "mcp__ccd_session__mark_chapter")
UUID_WRITES = tuple(UUID_SERVER + name for name in WRITES)
NAMED_WRITES = tuple(NAMED_SERVER + name for name in WRITES)
UUID_READS = tuple(UUID_SERVER + name for name in READS)
UUID_LOOKALIKES = tuple(UUID_SERVER + name for name in LOOKALIKES)
READS_WITHOUT_A_VERB = ("mcp__plugin_gitkraken_gitkraken__git_status", "mcp__Claude_Browser__browser_snapshot",
                        "mcp__Claude_Browser__browser_take_screenshot")
JIRA_SEEN_MATCHER = "^mcp__.*(getJiraIssue|executeRead|execute_read|jira_get_issue)"
NOT_UNDERSTOOD = "/sdlc jira SCRUM-\uff11"  # looks like a key, is not one


class McpGateTest(GateTest):
    def setUp(self):
        super().setUp()
        self.marker = self.home / "sdlc-gate" / "s1.jira"

    def mcp(self, tool, tool_input=None, **payload):  # payload: agent_id, agent_type
        return self.run_hook("mcp", {"tool_name": tool, "tool_input": tool_input or {}, **payload})

    def denied(self, tool, tool_input=None):
        return bool(self.mcp(tool, tool_input).stdout)

    def denied_among(self, tools):
        return list(filter(self.denied, tools))

    def jira_run(self):
        self.prompt("/sdlc jira SCRUM-123")

    def jira_run_approved(self):
        self.jira_run()
        (self.home / "sdlc-gate" / "s1.jira-intake").unlink()  # as if the ticket's label had been seen
        self.prompt("approve plan")

    def jira_folder(self, slug="jira-scrum-123"):
        (self.project / ".sdlc" / slug).mkdir(parents=True)
