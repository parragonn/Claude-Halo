"""Fournisseurs de réponses factices : écho (M3) puis démo markdown (M6)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator

from halo.ai.ports import PromptRequest
from halo.core import events as ev


def _chunks(text: str, size: int) -> Iterator[str]:
    for start in range(0, len(text), size):
        yield text[start : start + size]


_DEMO_ANSWERS = (
    """## Les quaternions, simplement

Un **quaternion** est une extension des nombres complexes : `q = w + xi + yj + zk`.

Trois usages concrets :

- **Rotations 3D** sans blocage de cardan (*gimbal lock*) ;
- **Interpolation** fluide entre orientations (slerp) ;
- **Stabilité numérique** : pas de matrices à re-orthogonaliser.

```python
import numpy as np

def slerp(q0, q1, t):
    dot = np.clip(np.dot(q0, q1), -1.0, 1.0)
    theta = np.arccos(dot) * t
    q2 = q1 - q0 * dot
    return q0 * np.cos(theta) + q2 / np.linalg.norm(q2) * np.sin(theta)
```

> « Les quaternions arrivent des couloirs de l'algèbre comme un fantôme. »
> — Lord Kelvin, à peu près.
""",
    """### Pour aller plus loin

| Outil | Usage | Verdict |
|---|---|---|
| `numpy-quaternion` | calcul scientifique | solide |
| `scipy.spatial.transform` | rotations usuelles | recommandé |
| fait main | apprentissage | formateur |

1. Commence par visualiser une rotation d'axe `z` ;
2. Compare matrice vs quaternion sur 1 000 compositions ;
3. Mesure la dérive numérique des deux approches.

*Voilà — redis « Claude, … » pour enchaîner.*
""",
    """**Bien sûr.** Trois points clés à retenir :

- la *partie réelle* encode l'angle (`cos θ/2`) ;
- la *partie vectorielle* encode l'axe (`sin θ/2 · axe`) ;
- la conjugaison `q v q⁻¹` applique la rotation.

Et c'est tout l'art : quatre nombres, zéro blocage.
""",
)


class DemoProvider:
    """Réponses markdown scriptées pour `halo --demo` : titres, code, tableau,
    citation — streamées à un rythme réaliste, sans réseau ni clé."""

    def __init__(self) -> None:
        self._calls = 0

    async def respond(
        self, request: PromptRequest, emit: Callable[[ev.Event], None]
    ) -> None:
        emit(ev.ResponseStarted())
        await asyncio.sleep(0.9)  # laisse voir l'orbe en mode réflexion
        answer = _DEMO_ANSWERS[self._calls % len(_DEMO_ANSWERS)]
        self._calls += 1
        for chunk in _chunks(answer, 8):
            emit(ev.ResponseDelta(text=chunk))
            await asyncio.sleep(0.012)
        emit(ev.ResponseCompleted())


class EchoProvider:
    """Bouclage local : accuse réception de la transcription."""

    def __init__(self, delay: float = 0.5) -> None:
        self._delay = delay

    async def respond(
        self, request: PromptRequest, emit: Callable[[ev.Event], None]
    ) -> None:
        emit(ev.ResponseStarted())
        await asyncio.sleep(self._delay)
        question = request.messages[-1]["content"] if request.messages else ""
        text = (
            "**Je t'ai bien entendu.** Tu as dit :\n\n"
            f"> {question}\n\n"
            "_Le vrai client Claude arrive au jalon M4 — ceci est un écho local._"
        )
        for chunk in _chunks(text, 6):
            emit(ev.ResponseDelta(text=chunk))
            await asyncio.sleep(0.03)
        emit(ev.ResponseCompleted())
