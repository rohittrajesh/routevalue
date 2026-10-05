import { useEffect, useId, useRef, useState } from "react";

import {
  createPlacesAutocompleteSession,
  type PlaceSuggestion,
  type PlacesAutocompleteSession,
} from "../integrations/googlePlaces";
import type { ResolvedLocationInput } from "../types/api";

const AUTOCOMPLETE_DEBOUNCE_MS = 250;

interface PlaceAutocompleteInputProps {
  label: string;
  placeholder: string;
  onLocationChange: (location: ResolvedLocationInput | null) => void;
}

function PlaceAutocompleteInput({
  label,
  placeholder,
  onLocationChange,
}: PlaceAutocompleteInputProps) {
  const inputId = useId();

  const sessionPromiseRef = useRef<Promise<PlacesAutocompleteSession> | null>(
    null,
  );

  const suggestionRequestIdRef = useRef(0);
  const selectionRequestIdRef = useRef(0);

  const [inputValue, setInputValue] = useState("");
  const [selectedLocation, setSelectedLocation] =
    useState<ResolvedLocationInput | null>(null);
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function getSession(): Promise<PlacesAutocompleteSession> {
    if (sessionPromiseRef.current === null) {
      sessionPromiseRef.current = createPlacesAutocompleteSession();
    }

    return sessionPromiseRef.current;
  }

  useEffect(() => {
    const normalizedInput = inputValue.trim();

    if (
      !normalizedInput ||
      (selectedLocation !== null &&
        inputValue === selectedLocation.display_name)
    ) {
      return;
    }

    const requestId = ++suggestionRequestIdRef.current;

    const timeoutId = window.setTimeout(() => {
      void (async () => {
        setIsLoading(true);
        setErrorMessage(null);

        try {
          const session = await getSession();

          const nextSuggestions =
            await session.fetchSuggestions(normalizedInput);

          if (requestId !== suggestionRequestIdRef.current) {
            return;
          }

          setSuggestions(nextSuggestions);
          setActiveIndex(nextSuggestions.length > 0 ? 0 : -1);
        } catch {
          if (requestId !== suggestionRequestIdRef.current) {
            return;
          }

          setSuggestions([]);
          setActiveIndex(-1);
          setErrorMessage("Unable to load place suggestions.");
        } finally {
          if (requestId === suggestionRequestIdRef.current) {
            setIsLoading(false);
          }
        }
      })();
    }, AUTOCOMPLETE_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [inputValue, selectedLocation]);

  async function selectSuggestion(suggestion: PlaceSuggestion) {
    const requestId = ++selectionRequestIdRef.current;

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const session = await getSession();

      const location = await session.resolveSuggestion(suggestion.id);

      if (requestId !== selectionRequestIdRef.current) {
        return;
      }

      suggestionRequestIdRef.current += 1;

      setSelectedLocation(location);
      setInputValue(location.display_name);
      setSuggestions([]);
      setActiveIndex(-1);

      onLocationChange(location);
    } catch {
      if (requestId !== selectionRequestIdRef.current) {
        return;
      }

      setErrorMessage("Unable to resolve the selected place.");
    } finally {
      if (requestId === selectionRequestIdRef.current) {
        setIsLoading(false);
      }
    }
  }

  function handleInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const nextValue = event.target.value;

    suggestionRequestIdRef.current += 1;
    selectionRequestIdRef.current += 1;

    if (selectedLocation !== null) {
      setSelectedLocation(null);
      onLocationChange(null);
    }

    setInputValue(nextValue);
    setSuggestions([]);
    setActiveIndex(-1);
    setIsLoading(false);
    setErrorMessage(null);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (suggestions.length === 0) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();

      setActiveIndex((currentIndex) =>
        currentIndex >= suggestions.length - 1 ? 0 : currentIndex + 1,
      );

      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();

      setActiveIndex((currentIndex) =>
        currentIndex <= 0 ? suggestions.length - 1 : currentIndex - 1,
      );

      return;
    }

    if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();

      const suggestion = suggestions[activeIndex];

      if (suggestion !== undefined) {
        void selectSuggestion(suggestion);
      }

      return;
    }

    if (event.key === "Escape") {
      setSuggestions([]);
      setActiveIndex(-1);
    }
  }

  const listboxId = `${inputId}-suggestions`;

  return (
    <div className="field place-autocomplete">
      <label className="place-autocomplete-label" htmlFor={inputId}>
        {label}
      </label>

      <div className="place-autocomplete-control">
        <input
          id={inputId}
          type="text"
          value={inputValue}
          placeholder={placeholder}
          autoComplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={suggestions.length > 0}
          aria-controls={listboxId}
          aria-activedescendant={
            activeIndex >= 0 ? `${inputId}-option-${activeIndex}` : undefined
          }
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          required
        />

        {selectedLocation !== null && (
          <span
            className="place-selected-indicator"
            aria-label="Resolved location selected"
          >
            Selected
          </span>
        )}
      </div>

      {suggestions.length > 0 && (
        <ul id={listboxId} className="place-suggestions" role="listbox">
          {suggestions.map((suggestion, index) => (
            <li
              id={`${inputId}-option-${index}`}
              key={suggestion.id}
              role="option"
              aria-selected={index === activeIndex}
              className={
                index === activeIndex
                  ? "place-suggestion active"
                  : "place-suggestion"
              }
            >
              <button
                type="button"
                onMouseDown={(event) => {
                  event.preventDefault();
                }}
                onClick={() => {
                  void selectSuggestion(suggestion);
                }}
              >
                <strong>{suggestion.primaryText}</strong>

                {suggestion.secondaryText !== null && (
                  <span>{suggestion.secondaryText}</span>
                )}
              </button>
            </li>
          ))}

          <li className="place-attribution" translate="no">
            Google Maps
          </li>
        </ul>
      )}

      {isLoading && (
        <span className="place-autocomplete-status" role="status">
          Finding places...
        </span>
      )}

      {errorMessage !== null && (
        <span className="place-autocomplete-error" role="alert">
          {errorMessage}
        </span>
      )}
    </div>
  );
}

export default PlaceAutocompleteInput;
