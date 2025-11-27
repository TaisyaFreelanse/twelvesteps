from fastapi import Depends, FastAPI, HTTPException, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv
import traceback

from api.dependencies import CurrentUserContext, get_current_user, get_db, get_db_session
from api.schemas import (
    AnswerRequest,
    ChatRequest,
    ChatResponse,
    ProfileUpdateRequest,
    StatusResponse,
    StepResponse,
    TelegramAuthRequest,
    TelegramAuthResponse,
    UserSchema,
    build_user_schema,
    # Add these two new schemas:
    SosRequest, 
    SosResponse
)
from api.steps import StepFlowService
# Ensure handle_sos is imported here (assuming you placed it in chat_service)
from core.chat_service import handle_chat, handle_sos 
from services.status import StatusService
from services.users import UserService

load_dotenv()

app = FastAPI(title="12STEPS Chat API")

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    try:
        reply = await handle_chat(payload.telegram_id, payload.message, payload.debug)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))
    return reply


# --- NEW SOS ENDPOINT ---
@app.post("/sos", response_model=SosResponse)
async def sos_endpoint(payload: SosRequest) -> SosResponse:
    """
    Generates a helpful example answer based on the user's last context 
    and personalization settings.
    """
    try:
        # Call the function we created in the previous step
        reply_text = await handle_sos(payload.telegram_id)
        return SosResponse(reply=reply_text)
    except RuntimeError as e:
        # Handle specific errors (like User not found)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))
# ------------------------


@app.post("/auth/telegram", response_model=TelegramAuthResponse)
async def authenticate_via_telegram(
    payload: TelegramAuthRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TelegramAuthResponse:
    service = UserService(session)
    user, is_new = await service.authenticate_telegram(
        telegram_id=payload.telegram_id,
        username=payload.username,
        first_name=payload.first_name,
    )
    return TelegramAuthResponse(
        user=build_user_schema(user), is_new=is_new, access_token=user.api_key or ""
    )


@app.patch("/me", response_model=UserSchema)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: CurrentUserContext = Depends(get_current_user),
) -> UserSchema:
    service = UserService(current_user.session)
    updates = payload.model_dump(exclude_unset=True)
    user = await service.update_profile(current_user.user, updates)
    return build_user_schema(user)


@app.get("/status", response_model=StatusResponse)
async def get_status(current_user: CurrentUserContext = Depends(get_current_user)) -> StatusResponse:
    service = StatusService(current_user.session)
    status_payload = await service.get_status_for_user(current_user.user)
    return StatusResponse(**status_payload)

# --- Steps Endpoints ---

@app.get("/steps/next", response_model=StepResponse)
async def get_next_step_question(
    current_context: CurrentUserContext = Depends(get_current_user) 
):
    """
    Retrieves the next question for the user.
    """
    service = StepFlowService(current_context.session)
    
    question_text = await service.get_next_question_for_user(current_context.user.id)
    
    if not question_text:
        return StepResponse(message="Program completed.", is_completed=True)
        
    return StepResponse(
        message=question_text,
        is_completed=False
    )


@app.post("/steps/answer")
async def submit_answer(
    answer_data: AnswerRequest,
    current_context: CurrentUserContext = Depends(get_current_user)
):
    """
    Submits an answer to the currently active question (Tail).
    """
    service = StepFlowService(current_context.session)
    
    success = await service.save_user_answer(current_context.user.id, answer_data.text)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="No active question found to answer. Please call /steps/next first."
        )
    
    return {"status": "success", "message": "Answer saved."}

