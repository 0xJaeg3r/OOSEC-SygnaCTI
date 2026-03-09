import os
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat, OpenAIResponses
from agno.models.anthropic import Claude
from agno.models.google import Gemini
from agno.team.team import Team
from agno.team.mode import TeamMode
from agno.tools.tavily import TavilyTools
from agno.tools.file import FileTools
from tools import CTI_TOOLS, TELEGRAM_SEARCH_TOOLS
from dark_web_search_tool import search_dark_web, browse_onion_site
from agno.tools.mcp import MultiMCPTools, MCPTools
from agno.compression.manager import CompressionManager
from prompt import *
load_dotenv()

SYGNA_DIR = Path.home() / ".sygnacti"
SYGNA_DIR.mkdir(exist_ok=True)

class CtiAgentSystem:
    """
    Complete and comprehensive Cyber Threat Intelligence agent with hierarchical delegation.
    Manger coordinates special agents for complete CTI activity

    """

##Give the agent a spec sheet

    def __init__(
            self,
            model_name: str = "gpt-5.2",
            use_memory: bool = False,
            use_storage: bool = False,
            use_mcp: bool = False,
            mcp_servers: Optional[List[Dict]] = None,
    ):
        ##Give agent a mind
        self.model_name = model_name
        self.model = self._get_model(model_name)
        self.use_memory = use_memory
        self.use_storage = use_storage
        self.use_mcp = use_mcp
        self.mcp_servers = mcp_servers or []
        self.mcp_tools = None

    ## Give agent base tools
        self.base_tools = [
            TavilyTools(), # Web search but will need an API Key remember
            FileTools(base_dir=Path("."),
                    enable_save_file=True,
                    enable_delete_file=False)
            
        ]
    
    ## Initialize all  tools
        self.all_tools = self._initialize_tools()
    

    ## Set up storage
        self.storage_db = None
        if use_storage:
            storage_path = SYGNA_DIR / "agent_storage.db"
            self.storage_db = SqliteDb(db_file=str(storage_path))
    
    #Set up memory
        self.memory_db = None
        if use_memory:
            memory_path = SYGNA_DIR / "agent_memory.db"
            self.memory_db = SqliteDb(db_file=str(memory_path))

     # Token limit management
        self.compression_manager = CompressionManager(
            model=OpenAIResponses(id="gpt-4o-mini"),
            compress_tool_results=True,
            compress_tool_results_limit=2,
            compress_token_limit=5000,
        )

    # Create specialized agents and team
        self._create_all_agents()
        self._create_cti_team()
        
    ##  Create mind for agent - Create model selector
    def _get_model(self, model_id: str):
        """
        Gets the right model based on model id
        """

        if "claude" in model_id.lower():
            return Claude(id=model_id)
        elif "gpt" in model_id.lower() or "o1" in model_id.lower(
        ) or "o3" in model_id.lower():
            return OpenAIChat(id=model_id)
        elif "gemini" in model_id.lower():
            return Gemini(id=model_id)
        else:
            try:
                from agno.models.litellm import LiteLLM
                return LiteLLM(id=model_id, name="LiteLLM")
            except ImportError:
                #Fallback to OpenAI
                return OpenAIChat(id=model_id)
    
    ## Create the initialize tools helper function
    def _initialize_tools(self):
        """Initialize tools including MCP Servers (Optional)"""
        tools = CTI_TOOLS + self.base_tools

        # Add MCP tools if enabled and servers configured
        if self.use_mcp and self.mcp_servers:
            try:
                #Separate command-based and URL-based servers
                commands = []
                url_servers = []

                for server in self.mcp_servers:
                    if 'command' in server:
                        commands.append(server['command'])
                    elif 'url' in server:
                        url_servers.append(server)

                # Add command-based servers via MultiMCPTools
                if commands:
                    self.mcp_tools = MultiMCPTools(commands)
                    tools.append(self.mcp_tools)

                #Add URL-based servers individually
                for url_server in url_servers :
                    try:
                        mcp_tool = MCPTools(
                            url=url_server['url'],
                            transport=url_server.get('transport','streamable-http')
                        )
                        tools.append(mcp_tool)
                    except Exception as e:
                        print(
                            f"Warning: Failed to initialize MCP Server {url_server.get('name', 'unknown')}: {e}"
                        )

            except Exception as e:
                print (f" Warning: Failed to initialize MCP tools: {e}")
            
        return tools
    
   
    ## Create specialized CTI agents

    def _create_all_agents(self):
        """
        Docstring for _create_all_agents
        
        :param self: Description
        """

        agent_kwargs = {
            "model": self.model,
            "tools": self.all_tools
        }

        # Add storage databse if enabled
        if self.storage_db:
            agent_kwargs["db"] = self.storage_db
            agent_kwargs["add_history_to_context"] = True

        # Add memory on top of storage if enabled
        if self.memory_db:
            agent_kwargs["db"] = self.memory_db
            agent_kwargs["enable_user_memories"] = True
            agent_kwargs["add_history_to_context"] = True


        #Create specialized agents

        self.telegram_search_agent = Agent(
            name="Telegram Recon Specialist",
            role="Specializes in performing searches on telegram channels for threat intel",
            instructions=[TELEGRAM_AGENT_PROMPT],
            model=self.model,
            tools=TELEGRAM_SEARCH_TOOLS,
            add_datetime_to_context=True,
            markdown=True,
            compression_manager= self.compression_manager
        )

        # Dark web pipeline: 4 focused agents with scoped tools
        # Manager delegates to them in order: refiner -> searcher -> filter -> browser

        self.dark_web_query_refiner = Agent(
            name="Dark Web Query Refiner",
            role="Optimize search queries for dark web search engines",
            instructions=[DARK_WEB_QUERY_REFINER_PROMPT],
            model=self.model,
            markdown=False,
            compression_manager= self.compression_manager
        )

        self.dark_web_searcher = Agent(
            name="Dark Web Searcher",
            role="Execute dark web searches and return raw results",
            instructions=[DARK_WEB_SEARCHER_PROMPT],
            model=self.model,
            tools=[search_dark_web],
            add_datetime_to_context=True,
            markdown=False,
            compression_manager= self.compression_manager
        )

        self.dark_web_filter = Agent(
            name="Dark Web Results Filter",
            role="Triage and select the most relevant dark web search results",
            instructions=[DARK_WEB_FILTER_PROMPT],
            model=self.model,
            markdown=False,
            compression_manager= self.compression_manager
        )

        self.dark_web_browser = Agent(
            name="Dark Web Browser",
            role="Browse .onion sites and extract threat intelligence",
            instructions=[DARK_WEB_BROWSER_PROMPT],
            model=self.model,
            tools=[browse_onion_site],
            add_datetime_to_context=True,
            markdown=True,
            compression_manager= self.compression_manager
        )


        self.web_search_agent = Agent(
            name="Web Search Agent",
            role="Cyber Threat Intelligence Web search",
            instructions=[WEB_SEARCH_AGENT],
            model=self.model,
            tools=[TavilyTools()],
            add_datetime_to_context=True,
            markdown=True,
            compression_manager= self.compression_manager
        )

        self.reporting_agent = Agent(
            name="CTI Reporter",
            role="Cyber Threat Intelligence Documentation",
            instructions=[CTI_REPORTING_AGENT],
            model=self.model,
            add_datetime_to_context=True,
            markdown=True,
            
        )



    
    def _create_cti_team(self):
        """
        Docstring for _create_cti_team
        
        :param self: Description
        """
        import uuid

        #Create persistent session ID to maintain context accross multiple interractions
        self.session_id = str(uuid.uuid4())

        #Team configuration - always add history to context for persistent conversion
        team_kwargs = {
            "name":"CTI Team",
            "mode": TeamMode.coordinate,
            "model": self.model,
            "respond_directly": False,
            "members": [
                self.web_search_agent,
                self.telegram_search_agent,
                self.reporting_agent,
                self.dark_web_query_refiner,
                self.dark_web_searcher,
                self.dark_web_filter,
                self.dark_web_browser,
            ],
            "markdown": True,
            "instructions": [CTI_MANAGER_AGENT_PROMPT],
            "show_members_responses": True,
            "share_member_interactions": True, # Members receive previous members' outputs from current run
            "add_history_to_context": True, # CRITICAL: ALways preserve conversation history
            "debug_mode": True,
            "debug_level": 2,

        }

        #Add memory to database if enabled (for persistent storage accross sessions)
        if self.memory_db:
            team_kwargs["db"] = self.memory_db
            team_kwargs["enable_user_memories"]= True
        
        self.cti_team = Team(**team_kwargs)
    
    def run_assessment(self, task: str, stream: bool = True, show_full_reasoning: bool = True, stream_events:bool = True):
        """Conduct a CTI task with persistent session context"""
        # Use persistent session_id to maintain context across multiple runs
        self.cti_team.print_response(
            task,
            stream=stream,
            session_id=self.session_id,
            show_full_reasoning=show_full_reasoning,
            stream_events=stream_events,
            
        )
    
    def get_agent(self, agent_type:  str):
        """Get a specific agent by type"""
        agents = {
            "telegram_search": self.telegram_search_agent,
            "web_search": self.web_search_agent,
            "reports": self.reporting_agent,
            "dark_web_query_refiner": self.dark_web_query_refiner,
            "dark_web_searcher": self.dark_web_searcher,
            "dark_web_filter": self.dark_web_filter,
            "dark_web_browser": self.dark_web_browser,
        }
        return agents.get(agent_type.lower())

def main():
    """Main execution example"""
    print("\n Initializing OSINT Agent System...\n")

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found!")
        print("\nPlease set your OpenAI API key:")
        print("1. Copy .env.example to .env")
        print("2. Add your API key to the .env file")
        print("3. Get an API key from: https://platform.openai.com/api-keys\n")
        return

    # Create security system
    system = CtiAgentSystem(model_name="gpt-5.2")
    example_task = """
    What is the latest news on ransomware this month. Perform a full cyber threat investigation on the recent ransomware landscape and submit a report.
    """ 

    system.run_assessment(example_task, stream=True, show_full_reasoning=True, stream_events=True)

if __name__ == "__main__":
    main()


