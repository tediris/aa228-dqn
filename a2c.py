import tensorflow as tf
from ple.games.pong import Pong
from ple import PLE
from collections import deque
import numpy as np
from skimage import color, transform, exposure

# def preprocess_observation(obs):
#     img = obs[::3, ::6] # crop and downsize
#     img = img.mean(axis=2) # to greyscale
#     img = (img - 128) / 128 - 1 # normalize from -1. to 1.
#     return img.reshape(96, 86, 1)

def preprocess_observation(observation):
    img = color.rgb2gray(observation)
    return img.reshape(80, 80, 1)

# init the game stuff
game = Pong(width=80, height=80)
p = PLE(game, fps=30, display_screen=True)
p.init()

game_actions = p.getActionSet()

# First let's build the two DQNs (online & target)
input_height = 80
input_width = 80
input_channels = 4
conv_n_maps = [32, 64, 64]
conv_kernel_sizes = [(8,8), (4,4), (3,3)]
conv_strides = [4, 2, 1]
conv_paddings = ["SAME"] * 3
conv_activation = [tf.nn.relu] * 3
pool_strides = [(2, 2), (1, 1), (1, 1)]
# n_hidden_in = 64 * 11 * 10  # conv3 has 64 maps of 11x10 each
# n_hidden_in = 6400
n_hidden_in = 64 * 3 * 3
# n_hidden = 512
n_hidden = 256
hidden_activation = tf.nn.relu
n_outputs = len(game_actions)  # 9 discrete actions are available
initializer = tf.contrib.layers.variance_scaling_initializer()

def q_network(X_state, name):
    prev_layer = X_state
    with tf.variable_scope(name) as scope:
        for n_maps, kernel_size, strides, padding, activation, pool_stride in zip(
                conv_n_maps, conv_kernel_sizes, conv_strides,
                conv_paddings, conv_activation, pool_strides):
            prev_layer = tf.layers.conv2d(
                prev_layer, filters=n_maps, kernel_size=kernel_size,
                strides=strides, padding=padding, activation=activation,
                kernel_initializer=initializer)
            # add in a max pool
            prev_layer = tf.layers.max_pooling2d(
                prev_layer,
                (2, 2),
                pool_stride,
                padding='valid',
                data_format='channels_last',
                name=None
            )
        debug_shape = prev_layer.get_shape()
        last_conv_layer_flat = tf.reshape(prev_layer, shape=[-1, n_hidden_in])

        hidden = tf.layers.dense(last_conv_layer_flat, n_outputs,
                                 activation=hidden_activation,
                                 kernel_initializer=initializer)
        policy = tf.nn.softmax(tf.layers.dense(hidden, n_outputs,
                                  kernel_initializer=initializer))
        value = tf.layers.dense(hidden, 1,
                                  kernel_initializer=initializer)
    # trainable_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES,
    #                                    scope=scope.name)
    # trainable_vars_by_name = {var.name[len(scope.name):]: var
    #                           for var in trainable_vars}
    return policy, value

X_state = tf.placeholder(tf.float32, shape=[None, input_height, input_width,
                                            input_channels])

policy, value = q_network(X_state, name="policy_value_net")

# We need an operation to copy the online DQN to the target DQN
# copy_ops = [target_var.assign(online_vars[var_name])
#             for var_name, target_var in target_vars.items()]
# copy_online_to_target = tf.group(*copy_ops)

# Now for the training operations
learning_rate = 0.001
momentum = 0.95

with tf.variable_scope("train"):
    X_action = tf.placeholder(tf.int32, shape=[None])
    y = tf.placeholder(tf.float32, shape=[None, 1])
    advantage = tf.stop_gradient(y - value)
    action_mask = tf.one_hot(X_action, n_outputs)
    prob_under_policy = tf.reduce_sum(policy * action_mask, 1)
    policy_loss = -advantage * tf.log(prob_under_policy + 1e-10)
    value_loss = (y - value) ** 2
    entropy = tf.reduce_sum(policy * tf.log(policy + 1e-10), axis=1, keep_dims=True)

    loss = tf.reduce_mean(policy_loss + 0.5 * value_loss + 0.01 * entropy)

    # error = tf.abs(y - q_value)
    # clipped_error = tf.clip_by_value(error, 0.0, 1.0)
    # linear_error = 2 * (error - clipped_error)
    # loss = tf.reduce_mean(tf.square(clipped_error) + linear_error)

    global_step = tf.Variable(0, trainable=False, name='global_step')
    optimizer = tf.train.MomentumOptimizer(
        learning_rate, momentum, use_nesterov=True)
    training_op = optimizer.minimize(loss, global_step=global_step)

init = tf.global_variables_initializer()
saver = tf.train.Saver(max_to_keep=10)

# Let's implement a simple replay memory
replay_memory_size = 50000
replay_memory = deque([], maxlen=replay_memory_size)

def sample_memories(batch_size):
    indices = np.random.permutation(len(replay_memory))[:batch_size]
    cols = [[], [], [], [], []] # state, action, reward, next_state, continue
    for idx in indices:
        memory = replay_memory[idx]
        for col, value in zip(cols, memory):
            col.append(value)
    cols = [np.array(col) for col in cols]
    return (cols[0], cols[1], cols[2].reshape(-1, 1), cols[3],
           cols[4].reshape(-1, 1))

# And on to the epsilon-greedy policy with decaying epsilon
eps_min = 0.1
eps_max = 1.0
eps_decay_steps = 500000

def epsilon_greedy(p_, step):
    # epsilon = max(eps_min, eps_max - (eps_max-eps_min) * step/eps_decay_steps)
    if np.random.rand() < epsilon:
        return np.random.randint(n_outputs) # random action
    else:
    #     # return np.argmax(q_values) # optimal action
        return np.random.choice(n_outputs, p=np.reshape(p_, (3))) # action sampled from p

# We need to preprocess the images to speed up training

# TensorFlow - Execution phase
training_start = 10000  # start training after 10,000 game iterations
discount_rate = 0.99
skip_start = 0  # Skip the start of every game (it's just waiting time).
batch_size = 100
iteration = 0  # game iterations
done = True # env needs to be reset

# We will keep track of the max Q-Value over time and compute the mean per game
loss_val = np.infty
game_length = 0
total_max_q = 0
mean_max_q = 0.0

verbosity = 1
learn_iterations = 4
number_steps = 1000000
copy_steps = 10000
save_steps = 100000
state = None

def create_initial_state():
    p.reset_game()
    obs1 = preprocess_observation(p.getScreenRGB())
    state = np.ones((80, 80, 3)) * -1
    state = np.concatenate((state, obs1), axis=2)
    # state = obs1
    # for _ in range(3):
    #     p.act(None)
    #     new_obs = preprocess_observation(p.getScreenRGB())
    #     state = np.concatenate((state, new_obs), axis=2)
    return state

with tf.Session() as sess:
    print("Session created, starting...")
    init.run()
    print("initialized network")
    # copy_online_to_target.run()
    print("Copying params")
    state = create_initial_state()
    while True:
        step = global_step.eval()
        if step >= number_steps:
            break
        iteration += 1
        epsilon = max(eps_min, eps_max - (eps_max-eps_min) * step/eps_decay_steps)
        if verbosity > 0:
            print("\rIteration {}   Training step {}/{} ({:.1f})%   "
                  "Loss {:5f}    Mean Max-Q {:5f}   Epsilon {:3f}".format(
            iteration, step, number_steps, step * 100 / number_steps,
            loss_val, mean_max_q, epsilon), end="")
        if p.game_over():
            p.reset_game()
            # re-initialize the state
            state = create_initial_state()

        # observation = p.getScreenRGB()
        # state = preprocess_observation(observation)

        # Online DQN evaluates what to do
        p_ = policy.eval(feed_dict={X_state: [state]})
        action = epsilon_greedy(p_, step)

        # Online DQN plays
        # obs, reward, done, info = env.step(action)
        reward = p.act(game_actions[action])
        next_obs = preprocess_observation(p.getScreenRGB())
        next_state = np.concatenate((state[:, :, 1:], next_obs), axis=2)
        done = p.game_over()

        # Let's memorize what happened
        replay_memory.append((state, action, reward, next_state, 1.0 - done))
        state = np.array(next_state)

        # if args.test:
        #     continue

        # Compute statistics for tracking progress (not shown in the book)
        total_max_q += p_.max()
        game_length += 1
        if done:
            mean_max_q = total_max_q / game_length
            total_max_q = 0.0
            game_length = 0

        if iteration < training_start or iteration % learn_iterations != 0:
            continue # only train after warmup period and at regular intervals

        # Sample memories and use the target DQN to produce the target Q-Value
        X_state_val, X_action_val, rewards, X_next_state_val, continues = (
            sample_memories(batch_size))
        # next_q_values = target_q_values.eval(
        #     feed_dict={X_state: X_next_state_val})
        # max_next_q_values = np.max(next_q_values, axis=1, keepdims=True)
        y_val = rewards

        # Train the online DQN
        _, loss_val = sess.run([training_op, loss], feed_dict={
            X_state: X_state_val, X_action: X_action_val, y: y_val})

        # Regularly copy the online DQN to the target DQN
        # if step % copy_steps == 0:
        #     copy_online_to_target.run()

        # And save regularly
        if step % save_steps == 0:
            saver.save(sess, "ckpts/a2c", global_step=step)
