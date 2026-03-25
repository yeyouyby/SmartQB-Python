import math
import random


class SimulatedAnnealingExamBuilder:
    def __init__(
        self,
        question_pool,
        target_score=100,
        target_difficulty=0.65,
        difficulty_weight=100.0,
    ):
        # pool is a list of dicts: {"id": 1, "score": 5, "difficulty": 0.5, "tags": ["math"]}
        self.pool = question_pool
        self.target_score = target_score
        self.target_difficulty = target_difficulty
        self.difficulty_weight = difficulty_weight

    def energy(self, state):
        # State is a subset of pool
        if not state:
            return float("inf")

        current_score = sum(q.get("score", 0) for q in state)
        current_diff = sum(q.get("difficulty", 0.5) for q in state) / len(state)

        # Penalty for deviation from target score and difficulty
        score_penalty = abs(current_score - self.target_score)
        diff_penalty = (
            abs(current_diff - self.target_difficulty) * self.difficulty_weight
        )

        return score_penalty + diff_penalty

    def get_neighbor(self, current_state):
        if not current_state:
            return random.sample(self.pool, min(10, len(self.pool)))  # nosec B311

        neighbor = current_state.copy()

        in_state_ids = {q["id"] for q in neighbor}
        available_candidates = [p for p in self.pool if p["id"] not in in_state_ids]

        # 0: Swap, 1: Add, 2: Remove
        # Choose operation based on available pool and current state
        if not available_candidates:
            operation = 2  # Must remove if no candidates left
        elif len(neighbor) <= 1:
            operation = 1  # Must add if only 1 item left
        else:
            operation = random.choice([0, 1, 2])  # nosec B311

        if operation == 0:  # Swap
            idx_to_remove = random.randint(0, len(neighbor) - 1)  # nosec B311
            neighbor.pop(idx_to_remove)
            neighbor.append(random.choice(available_candidates))  # nosec B311
        elif operation == 1:  # Add
            neighbor.append(random.choice(available_candidates))  # nosec B311
        elif operation == 2:  # Remove
            idx_to_remove = random.randint(0, len(neighbor) - 1)  # nosec B311
            neighbor.pop(idx_to_remove)

        return neighbor

    def build_exam(self, initial_temp=100.0, cooling_rate=0.99, max_iterations=1000):
        if not self.pool:
            raise ValueError("question pool is empty")

        # Initial guess based on score
        avg_score = sum(float(q.get("score", 1)) for q in self.pool) / len(self.pool)
        estimated_count = (
            max(1, round(self.target_score / avg_score))
            if avg_score > 0
            else min(20, len(self.pool))
        )
        n_initial = min(estimated_count, len(self.pool))

        current_state = random.sample(self.pool, n_initial)  # nosec B311
        current_energy = self.energy(current_state)

        best_state = current_state
        best_energy = current_energy

        temp = initial_temp

        for _ in range(max_iterations):
            neighbor = self.get_neighbor(current_state)
            neighbor_energy = self.energy(neighbor)

            # If neighbor is better, accept it
            if neighbor_energy < current_energy:
                current_state = neighbor
                current_energy = neighbor_energy

                if current_energy < best_energy:
                    best_state = current_state
                    best_energy = current_energy
            else:
                # Accept worse state with probability based on temp
                prob = math.exp((current_energy - neighbor_energy) / temp)
                if random.random() < prob:  # nosec B311
                    current_state = neighbor
                    current_energy = neighbor_energy

            temp *= cooling_rate

            if temp < 0.01:
                break

        return best_state
