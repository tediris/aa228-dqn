import matplotlib.pyplot as plt

rewards = [-7.95, -8.0, -8.0, -7.7, -7.05, -5.1, 5.25, 6.15, 5.8, 6.0]
training_iterations = [0, 25, 50, 75, 100, 125, 150, 175, 200, 225]

plt.plot(training_iterations, rewards)
plt.title("Average Reward over 20 Games")
plt.xlabel("Training Steps (Thousands)")
plt.ylabel("Average Reward");
plt.show()
