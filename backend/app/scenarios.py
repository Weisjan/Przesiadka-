from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from .database import get_session
from .models import Scenario, ScenarioInput, ScenarioRead

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])
SessionDependency = Annotated[Session, Depends(get_session)]


def find_scenario(scenario_id: int, session: Session) -> Scenario:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono scenariusza.")
    return scenario


@router.get("", response_model=list[ScenarioRead])
def list_scenarios(session: SessionDependency):
    return session.exec(select(Scenario).order_by(Scenario.id.desc())).all()


@router.get("/{scenario_id}", response_model=ScenarioRead)
def get_scenario(scenario_id: int, session: SessionDependency):
    return find_scenario(scenario_id, session)


@router.post("", response_model=ScenarioRead, status_code=201)
def create_scenario(data: ScenarioInput, session: SessionDependency, response: Response):
    scenario = Scenario.model_validate(data.model_dump(mode="json"))
    session.add(scenario)
    session.commit()
    session.refresh(scenario)
    response.headers["Location"] = f"/api/scenarios/{scenario.id}"
    return scenario


@router.put("/{scenario_id}", response_model=ScenarioRead)
def update_scenario(scenario_id: int, data: ScenarioInput, session: SessionDependency):
    scenario = find_scenario(scenario_id, session)
    scenario.sqlmodel_update(data.model_dump(mode="json"))
    session.add(scenario)
    session.commit()
    session.refresh(scenario)
    return scenario


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, session: SessionDependency) -> Response:
    scenario = find_scenario(scenario_id, session)
    session.delete(scenario)
    session.commit()
    return Response(status_code=204)
