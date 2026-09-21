"""Phase-6 Monte Carlo simulation package.

R1 owns the foundational contracts: the simulation contract version,
immutable simulation-domain state/environment, execution config and
assumption contracts, provenance vocabulary, deterministic simulation
identity/serialization, deterministic RNG infrastructure, and structural
result contracts. R3 adds the offline empirical parameter artifact/loader;
R4 adds the zero-noise deterministic race-evolution kernel; R5 adds the
stochastic Monte Carlo engine (empirical residual sampling, scalar oracle,
chunked vectorized execution, and frequency aggregation); R6 adds opt-in
historically plausible pit dynamics (target stint lengths, effective pit
loss, compound transitions, tyre-age resets) with domain-separated RNG and
descriptive pit diagnostics. Traffic/overtaking and reliability remain
deliberately deferred. R7 adds the evaluation-only historical-validation
protocol/metrics surface (``validation``); it is never imported by the
runtime kernel.

Dependency direction: ``errors`` is a leaf; ``state`` depends on errors;
``config``/``results`` depend on state; ``rng`` depends on errors + state;
``engine`` depends on state/params/results and imports no canonical data;
``monte_carlo`` depends on engine/rng/results/params and imports no canonical
data, winner model, feature engine, or replay cache.
"""

from v2.simulation.config import (
    ASSUMPTIONS_VERSION,
    MAX_MASTER_SEED,
    Assumptions,
    ParameterIdentity,
    SimulationConfig,
    simulation_request_identity,
)
from v2.simulation.engine import (
    CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES,
    ENGINE_VERSION,
    ENGINE_UNSUPPORTED_REASONS,
    INVALID_RUN_REASONS,
    SUPPORTED_TRACK_STATES,
    DeterministicRaceEngine,
    ExecutionPolicy,
    PaceParameterSelection,
    SelectedParameter,
    SimulationUnsupportedError,
    contemporaneous_roster_offenders,
    expected_lap_time_s,
    max_lap_events,
    select_pace_parameters,
)
from v2.simulation.errors import (
    SimulationContractError,
    SimulationError,
    SimulationRNGError,
    SimulationValidationError,
)
from v2.simulation.monte_carlo import (
    COMPOUND_TRANSITION_FAMILY,
    DEFAULT_CHUNK_SIZE,
    GLOBAL_COMPOUND_KEY,
    MONTE_CARLO_VERSION,
    PIT_DYNAMICS_VERSION,
    PIT_INVALID_REASONS,
    PIT_LOSS_FAMILY,
    PODIUM_POSITIONS,
    PROBABILITY_TOLERANCE,
    RELIABILITY_DEFERRED_NOTE,
    RESIDUAL_FAMILY,
    RESIDUAL_INDEPENDENCE_ASSUMPTION,
    RESIDUAL_INDEPENDENCE_NOTE,
    STINT_LENGTH_FAMILY,
    TRAFFIC_DEFERRED_NOTE,
    MonteCarloDiagnostics,
    MonteCarloEngine,
    PitParameterSet,
    ResidualSampler,
    max_residual_draws,
    run_trajectory_scalar,
    select_pit_parameters,
    select_residual_sampler,
)
from v2.simulation.params import (
    ELIGIBILITY_RULE_VERSION,
    ESTIMATOR_VERSION,
    PARAMETER_CONTRACT_VERSION,
    PARAMETER_SET_ID,
    ParameterFamily,
    SimulationParameterSet,
    SupportEntry,
    load_simulation_parameters,
    parameter_storage_dir,
)
from v2.simulation.results import (
    DNF_POSITION,
    PROBABILITY_SEMANTICS,
    PROBABILITY_SEMANTICS_NOTE,
    DriverFinish,
    DriverSimulationSummary,
    FinishOrder,
    MonteCarloResult,
    PositionFrequency,
    SimulationRunResult,
)
from v2.simulation.rng import (
    MAX_SIMULATION_ID,
    SIMULATION_RNG_ALGORITHM,
    SIMULATION_RNG_DOMAINS,
    rng_for_domain,
    rng_for_simulation,
    seed_sequence_for_simulation,
)
from v2.simulation.validation import (
    R7_VALIDATION_VERSION,
    R7Protocol,
    default_protocol,
    is_contemporaneous,
)
from v2.simulation.state import (
    SIMULATION_CONTRACT_VERSION,
    DriverSimState,
    DriverStatus,
    Provenance,
    SimulationEnvironment,
    SimulationState,
    canonical_json,
    canonical_sha256,
    driver_status_value,
    provenance_value,
)

__all__ = [
    "ASSUMPTIONS_VERSION",
    "COMPOUND_TRANSITION_FAMILY",
    "CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES",
    "DEFAULT_CHUNK_SIZE",
    "DNF_POSITION",
    "GLOBAL_COMPOUND_KEY",
    "MonteCarloDiagnostics",
    "PIT_DYNAMICS_VERSION",
    "PIT_INVALID_REASONS",
    "PIT_LOSS_FAMILY",
    "PitParameterSet",
    "RELIABILITY_DEFERRED_NOTE",
    "STINT_LENGTH_FAMILY",
    "TRAFFIC_DEFERRED_NOTE",
    "select_pit_parameters",
    "DeterministicRaceEngine",
    "ELIGIBILITY_RULE_VERSION",
    "ENGINE_UNSUPPORTED_REASONS",
    "ENGINE_VERSION",
    "ExecutionPolicy",
    "INVALID_RUN_REASONS",
    "MONTE_CARLO_VERSION",
    "MonteCarloEngine",
    "PODIUM_POSITIONS",
    "PROBABILITY_TOLERANCE",
    "PaceParameterSelection",
    "RESIDUAL_FAMILY",
    "RESIDUAL_INDEPENDENCE_ASSUMPTION",
    "RESIDUAL_INDEPENDENCE_NOTE",
    "ResidualSampler",
    "SUPPORTED_TRACK_STATES",
    "SelectedParameter",
    "SimulationUnsupportedError",
    "contemporaneous_roster_offenders",
    "expected_lap_time_s",
    "max_lap_events",
    "max_residual_draws",
    "run_trajectory_scalar",
    "select_pace_parameters",
    "select_residual_sampler",
    "ESTIMATOR_VERSION",
    "MAX_MASTER_SEED",
    "MAX_SIMULATION_ID",
    "PARAMETER_CONTRACT_VERSION",
    "PARAMETER_SET_ID",
    "PROBABILITY_SEMANTICS",
    "PROBABILITY_SEMANTICS_NOTE",
    "SIMULATION_CONTRACT_VERSION",
    "SIMULATION_RNG_ALGORITHM",
    "SIMULATION_RNG_DOMAINS",
    "Assumptions",
    "DriverFinish",
    "DriverSimState",
    "DriverSimulationSummary",
    "DriverStatus",
    "FinishOrder",
    "MonteCarloResult",
    "ParameterFamily",
    "ParameterIdentity",
    "PositionFrequency",
    "Provenance",
    "SimulationConfig",
    "SimulationContractError",
    "SimulationEnvironment",
    "SimulationError",
    "SimulationParameterSet",
    "SimulationRNGError",
    "SimulationRunResult",
    "SimulationState",
    "SimulationValidationError",
    "SupportEntry",
    "canonical_json",
    "canonical_sha256",
    "driver_status_value",
    "load_simulation_parameters",
    "parameter_storage_dir",
    "provenance_value",
    "rng_for_domain",
    "rng_for_simulation",
    "seed_sequence_for_simulation",
    "simulation_request_identity",
    "R7Protocol",
    "R7_VALIDATION_VERSION",
    "default_protocol",
    "is_contemporaneous",
]
