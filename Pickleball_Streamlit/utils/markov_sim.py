import random

def simulate_match(p_win_a, p_win_b):
    score_a = 0
    score_b = 0
    serving_team = 'A'
    server_number = 2

    history_a = [0]
    history_b = [0]
    rallies = 0

    while True:
        if (score_a >= 11 or score_b >= 11) and abs(score_a - score_b) >= 2:
            break

        rallies += 1

        if serving_team == 'A':
            if random.random() < p_win_a:
                score_a += 1
            else:
                if server_number == 1:
                    server_number = 2
                else:
                    serving_team = 'B'
                    server_number = 1
        else:
            if random.random() < p_win_b:
                score_b += 1
            else:
                if server_number == 1:
                    server_number = 2
                else:
                    serving_team = 'A'
                    server_number = 1

        history_a.append(score_a)
        history_b.append(score_b)

    winner = "Team A" if score_a > score_b else "Team B"
    return winner, score_a, score_b, rallies, history_a, history_b