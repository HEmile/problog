1/5::a.
b(1)~beta(1,1):-a.
b(1)~beta(1,2):-\+a.
b(2)~beta(1,1):-a.
b(2)~beta(1,2):-\+a.
B::coin_flip(N):- B is b(1).
B::coin_flip(N):- B is b(2).


evidence(coin_flip(1), true).
evidence(coin_flip(2), false).
% query_density(b(N)).
query_density(b(1)).
query_density(b(2)).
