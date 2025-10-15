import numpy as np

# dummy values
centers = np.array([[1,1], [1,2], [2,1], [2,2]], dtype=float)
scale = 0.1
noise = np.random.normal(size=centers.shape, scale=0.1)
centers += noise
lines = np.array([[1,1,2,1], [2,1,2,2], [2,2,1,2], [1,2, 1,1], [1,1,2,2], [1,2,2,1]], dtype=float)

start = lines[...,:2]
end = lines[...,2:]

centers_ = centers.reshape(1,len(centers), 2) * np.ones((len(start), len(centers), 2))
sc_diff= np.linalg.norm(centers_ - np.expand_dims(start,axis=1), axis=-1)
ec_diff = np.linalg.norm(centers_ - np.expand_dims(end,axis=1), axis=-1)

sc = {str(cent):list(lines[np.where(sc_diff[...,i]<scale*2)]) for i, cent in enumerate(centers)}
ec = [sc[str(cent)].append(lines[np.where(ec_diff[...,i]<scale*2)]) for i, cent in enumerate(centers)]

print(sc)