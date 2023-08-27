import tensorflow as tf
import tensorflow_probability as tfp
from tqdm import tqdm
from controller.RL.utils.common import ReplayMemory, Transition

class SACController:
    def __init__(self, simulator):
        for i in range(50):
            simulator.step(0)
        self.sac = SAC(len(simulator.get_concated_features()), 0.0, simulator.heat_model.get_max_heating_power())

    def control(self, future_required_temperatures, future_outside_temperatures, future_energy_cost,
                previous_outside_temperatures, previous_inside_temperatures, previous_energy_consuption):
            future_min = [x[0] for x in future_required_temperatures]
            future_max = [x[1] for x in future_required_temperatures]
            state = future_min + future_max + future_outside_temperatures + future_energy_cost + previous_outside_temperatures + previous_inside_temperatures + previous_energy_consuption
            tf_state = tf.constant(state, name="State")
            tf_state = tf.reshape(tf_state, (1, -1))
            return self.sac.control(tf_state)

    def save(self, path):
        self.sac.policy.save(path + 'SAC_policy.h5')

    def load(self, path):
        self.sac.policy = tf.keras.models.load_model(path + 'SAC_policy.h5')

    def train(self, simulator):
        self.sac.train(simulator, init_step=20)



class SAC:
    def __init__(self, feature_size, min_value, max_value):
        self.min_value = min_value
        self.max_value = max_value
        self.policy = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation=tf.nn.relu, input_shape=(feature_size,)),
            tf.keras.layers.Dense(256, activation=tf.nn.relu),
            tf.keras.layers.Dense(1)
        ], name="Policy")
        self.log_std = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation=tf.nn.relu, input_shape=(feature_size,)),
            tf.keras.layers.Dense(256, activation=tf.nn.relu),
            tf.keras.layers.Dense(1)
        ], name="Std_log")
        self.q1 = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation=tf.nn.relu, input_shape=(feature_size+1,)),
            tf.keras.layers.Dense(256, activation=tf.nn.relu),
            tf.keras.layers.Dense(1)
        ], name="Q1_network")
        self.q2 = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation=tf.nn.relu, input_shape=(feature_size+1,)),
            tf.keras.layers.Dense(256, activation=tf.nn.relu),
            tf.keras.layers.Dense(1)
        ], name="Q2_network")
        self.value = tf.keras.Sequential([
            tf.keras.layers.Dense(256, activation=tf.nn.relu, input_shape=(feature_size,)),
            tf.keras.layers.Dense(256, activation=tf.nn.relu),
            tf.keras.layers.Dense(1)
        ], name="Value_network")

    def _scale_action(self,action):
        return (action+1)* ((self.max_value-self.min_value)/2) + self.min_value

    def deterministic_action(self, state):
        return self._scale_action(tf.math.tanh(self.policy(state)))

    def get_sample(self,state):
        min_std_log = -10
        max_std_log = 3
        distribution = tfp.distributions.Normal(loc=0, scale=1.0)
        sample = distribution.sample(1)
        sampled_action = tf.math.tanh(self.policy(state) + sample * tf.math.exp(tf.clip_by_value(self.log_std(state), min_std_log, max_std_log)))
        log_prob = distribution.log_prob(sample) - tf.math.log(1-tf.math.square(sampled_action)+tf.keras.backend.epsilon())
        return self._scale_action(sampled_action), log_prob

    def train(self,simulator,episode=1000, batch_size=128, gamma=0.98,init_step=0, alpha=0.1):
        huber_loss = tf.keras.losses.Huber()
        polyak = tf.constant([0.95])
        gamma = tf.constant([gamma])
        optimizer = tf.keras.optimizers.Adam()
        #replay_memory = ReplayMemory(20000)
        replay_memory = ReplayMemory(1000)
        target_value_network = tf.keras.models.clone_model(self.value)
        for ep in tqdm(range(episode)):
            simulator.reset()
            #reach initial state with enough history
            for i in range(init_step):
                simulator.step(0.0)
            done = False
            sum_reward=0.0
            while not(done):
                #act in the simulator
                state = tf.constant(simulator.get_concated_features(), dtype=tf.float32)
                state = tf.reshape(state,(1,-1))
                action, _ = self.get_sample(state)
                done, reward, _ = simulator.step(action.numpy()[0,0])
                sum_reward += reward
                next_state = tf.constant(simulator.get_concated_features(), dtype=tf.float32)
                if not(done):
                    replay_memory.push(state,tf.constant(action, dtype=tf.float32),next_state, tf.constant(reward, dtype=tf.float32))

                #actual training
                if len(replay_memory)>=batch_size:
                    transitions = replay_memory.sample(batch_size)
                    batch = Transition(*zip(*transitions))
                    state = tf.reshape(tf.stack(batch.state,axis=0),(batch_size,-1))
                    action = tf.reshape(tf.stack(batch.action,axis=0),(batch_size,-1))
                    next_state = tf.reshape(tf.stack(batch.next_state,axis=0),(batch_size,-1))
                    reward = tf.reshape(tf.stack(batch.reward,axis=0),(batch_size,-1))

                    with tf.GradientTape(persistent=True) as tape:
                        y_q = tf.stop_gradient(reward + gamma * target_value_network(next_state))
                        q1 = self.q_value(self.q1,state,action)
                        q2 = self.q_value(self.q2,state,action)
                        loss1 = tf.math.reduce_mean(huber_loss(y_q,q1))
                        loss2 = tf.math.reduce_mean(huber_loss(y_q,q2))
                    grad1 = tape.gradient(loss1, self.q1.trainable_variables)
                    optimizer.apply_gradients(zip(grad1, self.q1.trainable_variables))
                    grad2 = tape.gradient(loss2, self.q2.trainable_variables)
                    optimizer.apply_gradients(zip(grad2, self.q2.trainable_variables))

                    del tape

                    with tf.GradientTape(persistent=True) as tape:
                        sampled_action, log_prob = self.get_sample(state)
                        q1 = self.q_value(self.q1, state, sampled_action)
                        min_q = tf.minimum(q1,
                                           self.q_value(self.q2, state, sampled_action))
                        y_v = tf.stop_gradient(min_q - alpha * log_prob)

                        loss_value = tf.math.reduce_mean(huber_loss(y_v,self.value(state)))
                        loss_policy = tf.reduce_mean(alpha*log_prob - q1)

                    grad_value = tape.gradient(loss_value, self.value.trainable_variables)
                    optimizer.apply_gradients(zip(grad_value, self.value.trainable_variables))
                    grad_policy = tape.gradient(loss_policy, self.policy.trainable_variables)
                    optimizer.apply_gradients(zip(grad_policy, self.policy.trainable_variables))
                    grad_std = tape.gradient(loss_policy, self.log_std.trainable_variables)
                    optimizer.apply_gradients(zip(grad_std, self.log_std.trainable_variables))
                    del tape

                    #update target network
                    for var1, var2 in zip(target_value_network.trainable_variables,self.value.trainable_variables):
                        var1.assign(polyak * var1 + (1-polyak)* var2)
            print(sum_reward)

    def control(self, state):
        action = np.clip(self._scale_action(self.policy(state)), self.min_value, self.max_value)
        return action

    #@tf.function
    def q_value(self,model,state, action):
        concated = tf.concat([state, action], axis=-1)
        return model(concated)
        
