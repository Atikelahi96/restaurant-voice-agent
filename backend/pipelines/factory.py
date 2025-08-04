import os, logging
from dotenv import load_dotenv
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.frameworks.rtvi import RTVIProcessor, RTVIObserver
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from backend.utils.llm_tools import (
    TOOLS,
    system_prompt,
    list_menu,
    add_item,
    submit_order,
)
from pipecat.services.gemini_multimodal_live.gemini import (
    GeminiMultimodalLiveLLMService,
    InputParams,
)

log = logging.getLogger("factory")

# Load environment variables
load_dotenv(dotenv_path='backend/.env')

def build_pipeline(*, channel: str, transport):
    # Ensure the API key is set
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.error("GEMINI_API_KEY is missing in the environment variables.")
        raise ValueError("Missing GEMINI_API_KEY")

    try:
        # Initialize Gemini service
        gemini = GeminiMultimodalLiveLLMService(
            api_key=api_key,
            voice_id="Puck" if channel == "audio" else None,
            tools=TOOLS,
            params=InputParams(temperature=0.2, max_tokens=200),
            run_in_parallel=False,
        )

        # Register functions
        gemini.register_direct_function(list_menu)
        gemini.register_direct_function(add_item)
        gemini.register_direct_function(submit_order)

        # Set up the context and aggregator
        ctx = OpenAILLMContext(
            [{"role": "system", "content": system_prompt}],
            tools=TOOLS,
        )
        ctx_agg = gemini.create_context_aggregator(ctx)

        # Create the pipeline
        r = RTVIProcessor()
        pipe = Pipeline([
            transport.input(),
            r,
            ctx_agg.user(),
            gemini,
            transport.output(),
            ctx_agg.assistant(),
        ])

        return PipelineTask(
            pipe,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            observers=[RTVIObserver(r)],
        )
    except Exception as e:
        log.error(f"Failed to build pipeline: {str(e)}")
        raise

