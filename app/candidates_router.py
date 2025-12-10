from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import crud, schemas

router = APIRouter()

@router.get("/candidates", response_model=List[schemas.CandidateOut])
def read_candidates(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db)
):
    candidates = crud.get_candidates(db, skip=skip, limit=limit)
    return candidates

@router.get("/candidates/{candidate_id}", response_model=schemas.CandidateOut)
def read_candidate(candidate_id: int, db: Session = Depends(get_db)):
    db_candidate = crud.get_candidate(db, candidate_id=candidate_id)
    if db_candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return db_candidate

@router.post("/candidates", response_model=schemas.CandidateOut, status_code=201)
def create_candidate(candidate: schemas.CandidateCreate, db: Session = Depends(get_db)):
    return crud.create_candidate(db=db, candidate=candidate)

@router.put("/candidates/{candidate_id}", response_model=schemas.CandidateOut)
def update_candidate(
    candidate_id: int,
    candidate: schemas.CandidateUpdate,
    db: Session = Depends(get_db)
):
    db_candidate = crud.update_candidate(db, candidate_id=candidate_id, candidate=candidate)
    if db_candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return db_candidate

@router.delete("/candidates/{candidate_id}", status_code=204)
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    success = crud.delete_candidate(db, candidate_id=candidate_id)
    if not success:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return None
