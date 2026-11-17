package api

import (
	"encoding/json"
	"errors"
	"net/http"

	"instances/internal/httpx"
	"instances/internal/refs"
	"instances/internal/server"
)

// Event applies one event from `catalog`. Shapes: backend/contracts/.
func (h *Handlers) Event(r *server.Request) error {
	body, err := httpx.ReadValue(r.R)
	if err != nil {
		return err
	}
	result, err := h.Refs.ApplyEvent(r.R.Context(), json.RawMessage(body))
	var badEvent *refs.BadEvent
	if errors.As(err, &badEvent) {
		// Retrying cannot help a malformed event, so this is not a 5xx.
		return httpx.Detail(http.StatusBadRequest, badEvent.Message)
	}
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusOK, map[string]string{"result": result})
	return nil
}

// Retire deletes a copy before `catalog` deletes its type: 409 while instances use it.
func (h *Handlers) Retire(r *server.Request) error {
	kind := r.Param("kind")
	if !refs.IsKnown(kind) {
		return httpx.NotFound()
	}
	id, _ := server.ParseGUID(r.Param("refId"))
	err := h.Refs.Retire(r.R.Context(), kind, id)
	if errors.Is(err, refs.ErrInUse) {
		return httpx.Detail(http.StatusConflict, "in use")
	}
	if err != nil {
		return err
	}
	httpx.WriteJSON(r.W, http.StatusNoContent, nil)
	return nil
}
